from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.classifier import ClassifierApiVersion, ClassifierSkillLinkerConfig
from app.agent.skill_linker.classifier.adapters import ClassifierAdapterV1, ClassifierAdapterV2
from app.agent.skill_linker.classifier.client import ClassifierClient, ClassifierServiceError, \
    ClassifierV2Response
from app.agent.skill_linker.classifier.linker import ClassifierSkillLinker
from app.agent.skill_linker.reranker import LlmRerankerServiceError, SkillReranker
from app.countries import Country


def _match(entity_type: str, uuid: str, score: float) -> dict:
    return {"entity_type": entity_type, "similarity_score": score, "entity": {"uuid": uuid, "preferred_label": uuid}}


def _entity(entity_type: str, matches: list[dict]) -> dict:
    return {"entity_type": entity_type, "surface_form": "", "span": {"start": 0, "end": 1}, "matches": matches}


def _given_v2_client() -> MagicMock:
    """A classifier with best matches a (0.9) and c (0.8), and remaining match b (0.5)."""
    given_client = MagicMock(spec=ClassifierClient)
    given_client.classify_v2 = AsyncMock(return_value=ClassifierV2Response.model_validate({"entities": [
        _entity("skill", [_match("skill", "a", 0.9), _match("skill", "b", 0.5)]),
        _entity("skill", [_match("skill", "c", 0.8)]),
    ]}))
    return given_client


def _given_reranker(**kwargs) -> MagicMock:
    reranker = MagicMock(spec=SkillReranker)
    reranker.rerank = AsyncMock(**kwargs)
    return reranker


async def _execute(linker: ClassifierSkillLinker):
    return await linker.execute(experience_title="Baker",
                                responsibilities=["I bake bread", "I sell pastries"],
                                company_name="Bakery",
                                country_of_interest=Country.UNSPECIFIED,
                                work_type=WorkType.FORMAL_SECTOR_WAGED_EMPLOYMENT)


class TestInit:
    def test_v1_requires_skill_search_service(self):
        # GIVEN the v1 classifier API version and no skill search service
        # WHEN the classifier linker is created
        # THEN a ValueError is raised
        with pytest.raises(ValueError):
            ClassifierSkillLinker(version=ClassifierApiVersion.V1, client=MagicMock())

    @pytest.mark.parametrize("version, expected_adapter_class", [
        (ClassifierApiVersion.V1, ClassifierAdapterV1),
        (ClassifierApiVersion.V2, ClassifierAdapterV2),
    ])
    def test_uses_the_adapter_of_the_version(self, version: ClassifierApiVersion, expected_adapter_class: type):
        # GIVEN a classifier API version
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
        linker = ClassifierSkillLinker(version=ClassifierApiVersion.V2, client=given_client,
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
        linker = ClassifierSkillLinker(version=ClassifierApiVersion.V2, client=given_client)

        # WHEN the linker is executed
        actual_response = await _execute(linker)

        # THEN no skills are returned and no exception is raised
        assert actual_response.top_skills == []
        assert actual_response.remaining_skills == []


class TestExecuteWithReranker:
    @pytest.mark.asyncio
    async def test_reranked_skills_are_the_top_skills(self):
        # GIVEN a reranker that picks b, then c
        given_reranker = MagicMock(spec=SkillReranker)

        async def rerank(**kwargs):
            by_uuid = {skill.UUID: skill for skill in kwargs["candidates"]}
            return [by_uuid["b"], by_uuid["c"]]

        given_reranker.rerank = AsyncMock(side_effect=rerank)
        linker = ClassifierSkillLinker(version=ClassifierApiVersion.V2, client=_given_v2_client(),
                                       config=ClassifierSkillLinkerConfig(number_of_top_skills=4),
                                       reranker=given_reranker)

        # WHEN the linker is executed
        actual_response = await _execute(linker)

        # THEN the reranker got every candidate, sorted by score, and the experience
        actual_kwargs = given_reranker.rerank.call_args.kwargs
        assert [skill.UUID for skill in actual_kwargs["candidates"]] == ["a", "c", "b"]
        assert actual_kwargs["experience_title"] == "Baker"
        assert actual_kwargs["responsibilities"] == ["I bake bread", "I sell pastries"]
        assert actual_kwargs["max_skills"] == 4
        # AND the reranked skills are the top skills, in the reranker's order
        assert [skill.UUID for skill in actual_response.top_skills] == ["b", "c"]
        # AND the other candidates are the remaining skills
        assert [skill.UUID for skill in actual_response.remaining_skills] == ["a"]

    @pytest.mark.asyncio
    async def test_sends_at_most_max_rerank_candidates(self):
        # GIVEN a linker that sends at most 2 candidates to the reranker, which picks c
        given_reranker = MagicMock(spec=SkillReranker)

        async def rerank(**kwargs):
            return [skill for skill in kwargs["candidates"] if skill.UUID == "c"]

        given_reranker.rerank = AsyncMock(side_effect=rerank)
        linker = ClassifierSkillLinker(version=ClassifierApiVersion.V2, client=_given_v2_client(),
                                       config=ClassifierSkillLinkerConfig(max_rerank_candidates=2),
                                       reranker=given_reranker)

        # WHEN the linker is executed
        actual_response = await _execute(linker)

        # THEN only the 2 best scoring candidates are reranked
        assert [skill.UUID for skill in given_reranker.rerank.call_args.kwargs["candidates"]] == ["a", "c"]
        # AND the candidates that were not sent are still remaining skills
        assert [skill.UUID for skill in actual_response.top_skills] == ["c"]
        assert [skill.UUID for skill in actual_response.remaining_skills] == ["a", "b"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_reranker_behaviour", [
        {"side_effect": LlmRerankerServiceError("boom")},
        {"return_value": []},
    ], ids=["reranker error", "reranker picks nothing"])
    async def test_keeps_the_classifier_ranking(self, given_reranker_behaviour: dict):
        # GIVEN a reranker that fails or picks nothing
        linker = ClassifierSkillLinker(version=ClassifierApiVersion.V2, client=_given_v2_client(),
                                       config=ClassifierSkillLinkerConfig(number_of_top_skills=1),
                                       reranker=_given_reranker(**given_reranker_behaviour))

        # WHEN the linker is executed
        actual_response = await _execute(linker)

        # THEN the classifier ranking is kept and no exception is raised
        assert [skill.UUID for skill in actual_response.top_skills] == ["a"]
        assert [skill.UUID for skill in actual_response.remaining_skills] == ["c", "b"]

    @pytest.mark.asyncio
    async def test_does_not_call_the_reranker_without_candidates(self):
        # GIVEN a classifier that matches nothing
        given_client = MagicMock(spec=ClassifierClient)
        given_client.classify_v2 = AsyncMock(return_value=ClassifierV2Response.model_validate({"entities": []}))
        given_reranker = _given_reranker(return_value=[])
        linker = ClassifierSkillLinker(version=ClassifierApiVersion.V2, client=given_client, reranker=given_reranker)

        # WHEN the linker is executed
        actual_response = await _execute(linker)

        # THEN the reranker is not called
        given_reranker.rerank.assert_not_called()
        assert actual_response.top_skills == []
