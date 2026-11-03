from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.skill_linker.classifier.adapters.adapter_v2 import ClassifierAdapterV2
from app.agent.skill_linker.classifier.config import ClassifierSkillLinkerConfig
from app.agent.skill_linker.classifier.client import ClassifierClient, ClassifierV2Response


def _skill_match(uuid: str, label: str, score: float, skill_type: str = "skill/competence") -> dict:
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
            "skill_type": skill_type,
        },
    }


def _occupation_match(uuid: str, label: str, score: float) -> dict:
    return {
        "entity_type": "occupation",
        "similarity_score": score,
        "entity": {"uuid": uuid, "preferred_label": label, "esco_code": "1234"},
    }


def _entity(entity_type: str, surface_form: str, matches: list[dict]) -> dict:
    return {"entity_type": entity_type, "surface_form": surface_form, "span": {"start": 0, "end": 1},
            "matches": matches}


def _given_adapter(entities: list[dict], config: ClassifierSkillLinkerConfig | None = None):
    given_response = ClassifierV2Response.model_validate({
        "entities": entities,
        "metadata": {"taxonomy_model_id": "taxonomy-model"},
    })
    given_client = MagicMock(spec=ClassifierClient)
    given_client.classify_v2 = AsyncMock(return_value=given_response)
    return ClassifierAdapterV2(client=given_client, config=config or ClassifierSkillLinkerConfig()), given_client


class TestClassify:
    @pytest.mark.asyncio
    async def test_calls_the_classifier_with_the_experience(self):
        # GIVEN an adapter configured with a top k and a min similarity
        adapter, given_client = _given_adapter([], ClassifierSkillLinkerConfig(top_k_per_entity=4, min_similarity=0.2))

        # WHEN an experience is classified
        await adapter.classify(experience_title="Baker", responsibilities=["I bake bread", "I sell pastries"])

        # THEN the v2 endpoint is called with the title, the responsibilities and the config
        given_client.classify_v2.assert_awaited_once()
        actual_call = given_client.classify_v2.await_args.kwargs
        assert actual_call["title"] == "Baker"
        assert actual_call["description"] == "- I bake bread\n- I sell pastries"
        assert set(actual_call["extract_entities"]) == {"skill", "occupation"}
        assert actual_call["top_k"] == 4
        assert actual_call["min_similarity"] == 0.2

    @pytest.mark.asyncio
    async def test_maps_matches_to_skill_candidates(self):
        # GIVEN a skill entity whose best match is not listed first, and a qualification entity
        adapter, _ = _given_adapter([
            _entity("skill", "sell pastries", [
                _skill_match("sell", "sell goods", 0.6),
                _skill_match("customer", "serve customers", 0.8),
            ]),
            _entity("qualification", "diploma", []),
        ])

        # WHEN an experience is classified
        actual_matches = await adapter.classify(experience_title="Baker", responsibilities=["I sell pastries"])

        # THEN the matches are skill candidates sorted by score, the first one being the best match
        assert [(c.skill.UUID, c.is_best_match) for c in actual_matches.skill_candidates] == [
            ("customer", True), ("sell", False)]
        # AND the taxonomy entities are mapped to skill entities
        actual_skill = actual_matches.skill_candidates[0].skill
        assert actual_skill.preferredLabel == "serve customers"
        assert actual_skill.originUUID == "origin-customer"
        assert actual_skill.UUIDHistory == ["customer"]
        assert actual_skill.altLabels == ["serve customers alt"]
        assert actual_skill.description == "serve customers description"
        assert actual_skill.skillType == "skill/competence"
        assert actual_skill.modelId == "taxonomy-model"
        assert actual_skill.score == 0.8

    @pytest.mark.asyncio
    async def test_unknown_skill_type_is_mapped_to_empty(self):
        # GIVEN a skill match with a skill type unknown to the taxonomy model
        adapter, _ = _given_adapter([_entity("skill", "bake", [_skill_match("bake", "bake", 0.9, "unknown")])])

        # WHEN an experience is classified
        actual_matches = await adapter.classify(experience_title="Baker", responsibilities=[])

        # THEN the skill type is empty
        assert actual_matches.skill_candidates[0].skill.skillType == ""

    @pytest.mark.asyncio
    async def test_occupations_are_title_candidates(self):
        # GIVEN occupation entities, one of them matched twice
        adapter, _ = _given_adapter([
            _entity("occupation", "Baker", [_occupation_match("baker", "baker", 0.7)]),
            _entity("occupation", "Pastry chef", [_occupation_match("cook", "cook", 0.5),
                                                   _occupation_match("pastry", "pastry chef", 0.9)]),
            _entity("occupation", "Bread maker", [_occupation_match("baker", "baker", 0.6)]),
            _entity("occupation", "Unknown", []),
        ])

        # WHEN an experience is classified
        actual_matches = await adapter.classify(experience_title="Baker", responsibilities=[])

        # THEN the best match of each occupation is a title candidate, sorted by score and deduplicated
        assert actual_matches.title_candidates == ["pastry chef", "baker"]
        # AND the occupations are not skill candidates
        assert actual_matches.skill_candidates == []
