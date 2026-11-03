from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.classifier import ClassifierSkillLinker, ClassifierSkillLinkerConfig
from app.agent.skill_linker.classifier.adapters import ClassifierAdapterV1, ClassifierAdapterV2
from app.agent.skill_linker.classifier.client import ClassifierClient, ClassifierServiceError, \
    ClassifierV2Response
from app.agent.skill_linker.config import SkillLinkerType
from app.countries import Country


def _match(entity_type: str, uuid: str, score: float) -> dict:
    return {"entity_type": entity_type, "similarity_score": score, "entity": {"uuid": uuid, "preferred_label": uuid}}


def _entity(entity_type: str, matches: list[dict]) -> dict:
    return {"entity_type": entity_type, "surface_form": "", "span": {"start": 0, "end": 1}, "matches": matches}


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

    @pytest.mark.parametrize("version, expected_adapter_class", [
        (SkillLinkerType.CLASSIFIER_V1, ClassifierAdapterV1),
        (SkillLinkerType.CLASSIFIER_V2, ClassifierAdapterV2),
    ])
    def test_uses_the_adapter_of_the_version(self, version: SkillLinkerType, expected_adapter_class: type):
        # GIVEN a classifier version
        # WHEN the classifier linker is created
        linker = ClassifierSkillLinker(version=version, client=MagicMock(), skill_search_service=MagicMock())

        # THEN it uses the adapter of that version
        assert isinstance(linker._adapter, expected_adapter_class)


class TestExecute:
    @pytest.mark.asyncio
    async def test_ranks_the_classifier_matches(self):
        # GIVEN a classifier v2 response with two skill entities and an occupation entity
        given_response = ClassifierV2Response.model_validate({"entities": [
            _entity("skill", [_match("skill", "a", 0.9), _match("skill", "b", 0.5)]),
            _entity("skill", [_match("skill", "c", 0.8)]),
            _entity("occupation", [_match("occupation", "baker", 0.9)]),
        ]})
        given_client = MagicMock(spec=ClassifierClient)
        given_client.classify_v2 = AsyncMock(return_value=given_response)
        # AND a classifier v2 linker that keeps 1 top skill
        linker = ClassifierSkillLinker(version=SkillLinkerType.CLASSIFIER_V2, client=given_client,
                                       config=ClassifierSkillLinkerConfig(number_of_top_skills=1))

        # WHEN the linker is executed
        actual_response = await _execute(linker)

        # THEN the best scoring best match is the top skill
        assert [skill.UUID for skill in actual_response.top_skills] == ["a"]
        # AND the other skills are the remaining skills, sorted by score
        assert [skill.UUID for skill in actual_response.remaining_skills] == ["c", "b"]
        # AND the occupations are the title candidates
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
