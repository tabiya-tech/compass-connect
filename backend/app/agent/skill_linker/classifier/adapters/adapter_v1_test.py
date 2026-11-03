from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.skill_linker.classifier.adapters.adapter_v1 import ClassifierAdapterV1
from app.agent.skill_linker.classifier.config import ClassifierSkillLinkerConfig
from app.agent.skill_linker.classifier.client import ClassifierClient, ClassifierV1Response
from app.vector_search.esco_entities import SkillEntity
from app.vector_search.esco_search_service import SkillSearchService


def _entity(entity_type: str, surface_form: str, linked_entities: list[dict]) -> dict:
    return {"entity_type": entity_type, "surface_form": surface_form, "span": {"start": 0, "end": 1},
            "linked_entities": linked_entities}


def _skill_entity(uuid: str, label: str, alt_labels: list[str] | None = None) -> SkillEntity:
    return SkillEntity(id=f"id-{uuid}", modelId="model", UUID=uuid, preferredLabel=label, altLabels=alt_labels or [],
                       description="", skillType="knowledge", score=0.0)


def _given_adapter(entities: list[dict], search_results: dict[str, list[SkillEntity]]):
    given_response = ClassifierV1Response.model_validate({"classification": {"entities": entities}, "metadata": {}})
    given_client = MagicMock(spec=ClassifierClient)
    given_client.classify_v1 = AsyncMock(return_value=given_response)
    given_search_service = MagicMock(spec=SkillSearchService)
    given_search_service.search = AsyncMock(side_effect=lambda *, query, k: search_results[query])
    adapter = ClassifierAdapterV1(client=given_client, config=ClassifierSkillLinkerConfig(),
                                  skill_search_service=given_search_service)
    return adapter, given_client, given_search_service


class TestClassify:
    @pytest.mark.asyncio
    async def test_resolves_labels_against_the_taxonomy(self):
        # GIVEN a classifier v1 response with labelled matches
        given_entities = [
            _entity("skill", "bake bread", [
                {"label": "bake bread", "similarity_score": 0.9, "taxonomy": "esco"},
                {"label": "unknown skill", "similarity_score": 0.3, "taxonomy": "esco"},
            ]),
            _entity("skill", "sell", [{"label": "sell goods", "similarity_score": 0.6, "taxonomy": "esco"}]),
            _entity("occupation", "Baker", [{"label": "baker", "similarity_score": 0.9, "code": "7512.1"}]),
        ]
        # AND a skill search service that
        #  - finds an exact alt label match for "bake bread" that is not the first search result,
        #  - finds no exact match for "sell goods",
        #  - finds nothing for "unknown skill"
        given_search_results = {
            "bake bread": [_skill_entity("other", "make cakes"), _skill_entity("bake", "baking", ["Bake bread"])],
            "sell goods": [_skill_entity("sell", "sell products"), _skill_entity("other", "make cakes")],
            "unknown skill": [],
        }
        adapter, given_client, _ = _given_adapter(given_entities, given_search_results)

        # WHEN an experience is classified
        actual_matches = await adapter.classify(experience_title="Baker", responsibilities=["I bake bread"])

        # THEN the v1 endpoint is called with the title and the responsibilities
        actual_call = given_client.classify_v1.await_args.kwargs
        assert actual_call["title"] == "Baker"
        assert actual_call["description"] == "- I bake bread"
        assert set(actual_call["extract_entities"]) == {"skill", "occupation"}
        # AND the labels are resolved to the taxonomy skills, preferring exact label matches,
        #     with the scores of the classifier, dropping the unresolvable label
        assert [(c.skill.UUID, c.skill.score, c.is_best_match) for c in actual_matches.skill_candidates] == [
            ("bake", 0.9, True), ("sell", 0.6, True)]
        # AND the occupations are returned as title candidates
        assert actual_matches.title_candidates == ["baker"]

    @pytest.mark.asyncio
    async def test_resolves_each_distinct_label_once(self):
        # GIVEN two entities matched to the same label
        given_entities = [
            _entity("skill", "bake bread", [{"label": "bake bread", "similarity_score": 0.9}]),
            _entity("skill", "baking", [{"label": "bake bread", "similarity_score": 0.7}]),
        ]
        adapter, _, given_search_service = _given_adapter(given_entities,
                                                          {"bake bread": [_skill_entity("bake", "bake bread")]})

        # WHEN an experience is classified
        actual_matches = await adapter.classify(experience_title="Baker", responsibilities=[])

        # THEN the label is searched once
        given_search_service.search.assert_awaited_once_with(query="bake bread", k=5)
        # AND each match is a skill candidate with its own score
        assert [(c.skill.UUID, c.skill.score) for c in actual_matches.skill_candidates] == [("bake", 0.9), ("bake", 0.7)]

    @pytest.mark.asyncio
    async def test_reads_the_alternative_match_keys(self):
        # GIVEN matches using the alternative label and score keys, and a match without a label
        given_entities = [
            _entity("skill", "bake bread", [{"preferred_label": " bake bread ", "score": 0.8}, {"score": 0.9}]),
        ]
        adapter, _, _ = _given_adapter(given_entities, {"bake bread": [_skill_entity("bake", "bake bread")]})

        # WHEN an experience is classified
        actual_matches = await adapter.classify(experience_title="Baker", responsibilities=[])

        # THEN the labelled match is resolved with its score, and the match without a label is ignored
        assert [(c.skill.UUID, c.skill.score, c.is_best_match) for c in actual_matches.skill_candidates] == [
            ("bake", 0.8, True)]
