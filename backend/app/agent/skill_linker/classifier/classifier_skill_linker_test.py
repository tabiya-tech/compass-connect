from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.classifier.classifier_client import ClassifierClient, ClassifierServiceError, ClassifierV1Response, \
    ClassifierV2Response
from app.agent.skill_linker.classifier.classifier_skill_linker import ClassifierSkillLinker, ClassifierSkillLinkerConfig
from app.agent.skill_linker.skill_linker_type import SkillLinkerType
from app.countries import Country
from app.vector_search.esco_entities import SkillEntity
from app.vector_search.esco_search_service import SkillSearchService


def _v2_skill_match(uuid: str, label: str, score: float) -> dict:
    return {
        "entity_type": "skill",
        "similarity_score": score,
        "entity": {
            "uuid": uuid,
            "origin_uuid": f"origin-{uuid}",
            "uuid_history": [uuid],
            "preferred_label": label,
            "origin_uri": f"http://esco/{uuid}",
            "alt_labels": [f"{label} alt"],
            "description": f"{label} description",
            "skill_type": "skill/competence",
        },
    }


def _v2_occupation_match(uuid: str, label: str, score: float) -> dict:
    return {
        "entity_type": "occupation",
        "similarity_score": score,
        "entity": {
            "uuid": uuid,
            "origin_uuid": f"origin-{uuid}",
            "uuid_history": [uuid],
            "preferred_label": label,
            "origin_uri": f"http://esco/{uuid}",
            "alt_labels": [],
            "description": "",
            "esco_code": "1234",
        },
    }


def _entity(entity_type: str, surface_form: str, **kwargs) -> dict:
    return {"entity_type": entity_type, "surface_form": surface_form, "span": {"start": 0, "end": 1}, **kwargs}


def _skill_entity(uuid: str, label: str, alt_labels: list[str] | None = None) -> SkillEntity:
    return SkillEntity(id=f"id-{uuid}", modelId="model", UUID=uuid, preferredLabel=label, altLabels=alt_labels or [],
                       description="", skillType="knowledge", score=0.0)


async def _execute(linker: ClassifierSkillLinker):
    return await linker.execute(experience_title="Baker",
                                responsibilities=["I bake bread", "I sell pastries"],
                                company_name="Bakery",
                                country_of_interest=Country.UNSPECIFIED,
                                work_type=WorkType.FORMAL_SECTOR_WAGED_EMPLOYMENT)


class TestInit:
    def test_rejects_non_classifier_version(self):
        # GIVEN the linking and ranking pipeline type
        # WHEN the classifier linker is created with it
        # THEN a ValueError is raised
        with pytest.raises(ValueError):
            ClassifierSkillLinker(version=SkillLinkerType.LINKING_AND_RANKING_PIPELINE, client=MagicMock())

    def test_v1_requires_skill_search_service(self):
        # GIVEN the v1 classifier type and no skill search service
        # WHEN the classifier linker is created
        # THEN a ValueError is raised
        with pytest.raises(ValueError):
            ClassifierSkillLinker(version=SkillLinkerType.CLASSIFIER_V1, client=MagicMock())


class TestV2:
    @pytest.mark.asyncio
    async def test_maps_and_ranks_matches(self):
        # GIVEN a classifier v2 response with two skill entities and one occupation entity
        given_response = ClassifierV2Response.model_validate({
            "entities": [
                _entity("skill", "bake bread", matches=[
                    _v2_skill_match("bake", "bake bread", 0.9),
                    _v2_skill_match("knead", "knead dough", 0.7),
                ]),
                _entity("skill", "sell pastries", matches=[
                    # the best match is listed second, the linker should not rely on the order
                    _v2_skill_match("sell", "sell goods", 0.6),
                    _v2_skill_match("customer", "serve customers", 0.8),
                ]),
                _entity("skill", "kneading", matches=[
                    # the same skill as a non-best match above, with a lower score
                    _v2_skill_match("knead", "knead dough", 0.5),
                ]),
                _entity("occupation", "Baker", matches=[_v2_occupation_match("baker", "baker", 0.95)]),
                _entity("qualification", "diploma", matches=[]),
            ],
            "metadata": {"classifier_version": "2", "ner_model": "ner", "nel_model_id": "nel",
                         "taxonomy_model_id": "taxonomy-model", "processing_time_ms": 1.0},
        })
        given_client = MagicMock(spec=ClassifierClient)
        given_client.classify_v2 = AsyncMock(return_value=given_response)
        # AND a classifier v2 linker that keeps 2 top skills
        linker = ClassifierSkillLinker(version=SkillLinkerType.CLASSIFIER_V2, client=given_client,
                                       config=ClassifierSkillLinkerConfig(number_of_top_skills=2))

        # WHEN the linker is executed
        actual_response = await _execute(linker)

        # THEN the classifier is called with the title and the responsibilities
        given_client.classify_v2.assert_awaited_once()
        actual_call = given_client.classify_v2.await_args.kwargs
        assert actual_call["title"] == "Baker"
        assert "I bake bread" in actual_call["description"] and "I sell pastries" in actual_call["description"]
        assert set(actual_call["extract_entities"]) == {"skill", "occupation"}
        # AND the top skills are the best match of each entity, sorted by score
        assert [skill.UUID for skill in actual_response.top_skills] == ["bake", "customer"]
        # AND the remaining skills are the other matches, deduplicated and sorted by score
        assert [skill.UUID for skill in actual_response.remaining_skills] == ["knead", "sell"]
        assert actual_response.remaining_skills[0].score == 0.7
        # AND the taxonomy entities are mapped to skill entities
        actual_skill = actual_response.top_skills[0]
        assert actual_skill.preferredLabel == "bake bread"
        assert actual_skill.originUUID == "origin-bake"
        assert actual_skill.UUIDHistory == ["bake"]
        assert actual_skill.altLabels == ["bake bread alt"]
        assert actual_skill.skillType == "skill/competence"
        assert actual_skill.modelId == "taxonomy-model"
        assert actual_skill.score == 0.9
        # AND the occupations are returned as title candidates
        assert actual_response.title_candidates == ["baker"]

    @pytest.mark.asyncio
    async def test_returns_empty_response_on_classifier_error(self):
        # GIVEN a classifier that fails
        given_client = MagicMock(spec=ClassifierClient)
        given_client.classify_v2 = AsyncMock(side_effect=ClassifierServiceError("boom"))
        linker = ClassifierSkillLinker(version=SkillLinkerType.CLASSIFIER_V2, client=given_client)

        # WHEN the linker is executed
        actual_response = await _execute(linker)

        # THEN no skills are returned and no exception is raised
        assert actual_response.top_skills == []
        assert actual_response.remaining_skills == []


class TestV1:
    @pytest.mark.asyncio
    async def test_resolves_labels_against_the_taxonomy(self):
        # GIVEN a classifier v1 response with labelled matches
        given_response = ClassifierV1Response.model_validate({
            "classification": {
                "entities": [
                    _entity("skill", "bake bread", linked_entities=[
                        {"label": "bake bread", "similarity_score": 0.9, "taxonomy": "esco"},
                        {"label": "unknown skill", "similarity_score": 0.3, "taxonomy": "esco"},
                    ]),
                    _entity("skill", "sell", linked_entities=[
                        {"label": "sell goods", "similarity_score": 0.6, "taxonomy": "esco"},
                    ]),
                    _entity("occupation", "Baker", linked_entities=[
                        {"label": "baker", "similarity_score": 0.9, "taxonomy": "esco", "code": "7512.1"},
                    ]),
                ],
                "entity_counts": {"skill": 2, "occupation": 1},
            },
            "metadata": {},
        })
        given_client = MagicMock(spec=ClassifierClient)
        given_client.classify_v1 = AsyncMock(return_value=given_response)

        # AND a skill search service that
        #  - finds an exact alt label match for "bake bread" that is not the first search result,
        #  - finds no exact match for "sell goods",
        #  - finds nothing for "unknown skill"
        given_search_results = {
            "bake bread": [_skill_entity("other", "make cakes"), _skill_entity("bake", "baking", ["Bake bread"])],
            "sell goods": [_skill_entity("sell", "sell products"), _skill_entity("other", "make cakes")],
            "unknown skill": [],
        }
        given_search_service = MagicMock(spec=SkillSearchService)
        given_search_service.search = AsyncMock(side_effect=lambda *, query, k: given_search_results[query])
        linker = ClassifierSkillLinker(version=SkillLinkerType.CLASSIFIER_V1, client=given_client,
                                       skill_search_service=given_search_service)

        # WHEN the linker is executed
        actual_response = await _execute(linker)

        # THEN the labels are resolved to the taxonomy skills, preferring exact label matches
        assert [skill.UUID for skill in actual_response.top_skills] == ["bake", "sell"]
        # AND the scores come from the classifier
        assert [skill.score for skill in actual_response.top_skills] == [0.9, 0.6]
        # AND the unresolvable label is dropped
        assert actual_response.remaining_skills == []
        # AND the occupations are returned as title candidates
        assert actual_response.title_candidates == ["baker"]
