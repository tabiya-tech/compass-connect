from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.agent_types import LLMStats
from app.agent.experience.timeline import Timeline
from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.classifier import ClassifierApiVersion, ClassifierSkillLinkerConfig
from app.agent.skill_linker.classifier.adapters import ClassifierAdapterV1, ClassifierAdapterV2
from app.agent.skill_linker.classifier.client import ClassifierClient, ClassifierServiceError, \
    ClassifierV2Response
from app.agent.skill_linker.classifier.linker import ClassifierSkillLinker
from app.agent.skill_linker.classifier.overview_generator import ExperienceOverviewGenerator, ExperienceOverviewResult
from app.agent.skill_linker.reranker import LlmRerankerServiceError, SkillReranker
from app.countries import Country
from app.vector_search.esco_entities import AssociatedSkillEntity, OccupationEntity, OccupationSkillEntity
from app.vector_search.esco_search_service import OccupationSkillSearchService


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


class TestExecuteWithOverviewGenerator:
    @pytest.mark.asyncio
    async def test_sends_overview_and_formalized_responsibilities_to_classifier_and_original_to_reranker(self):
        # GIVEN an overview generator returning an overview, formalized responsibilities, and LLM stats
        given_stats = [LLMStats(prompt_token_count=80, response_token_count=30, response_time_in_sec=0.4)]
        given_overview = "Worked as a baker in a neighborhood bakery in Cape Town."
        given_formal = ["Prepare artisan bread dough", "Handle retail pastry sales"]
        given_overview_generator = MagicMock(spec=ExperienceOverviewGenerator)
        given_overview_generator.execute = AsyncMock(return_value=ExperienceOverviewResult(
            overview=given_overview,
            professional_responsibilities=given_formal,
            llm_stats=given_stats,
        ))

        given_client = _given_v2_client()
        given_reranker = MagicMock(spec=SkillReranker)
        given_reranker.rerank = AsyncMock(side_effect=lambda **kwargs: kwargs["candidates"][:1])

        linker = ClassifierSkillLinker(
            version=ClassifierApiVersion.V2,
            client=given_client,
            reranker=given_reranker,
            overview_generator=given_overview_generator,
        )
        given_timeline = Timeline(start="2022", end="2024")
        given_qa = [("What did you bake?", "Bread and pastries")]

        # WHEN the linker is executed with full experience context
        actual_response = await linker.execute(
            experience_title="Baker",
            responsibilities=["I bake bread", "I sell pastries"],
            company_name="Bakery",
            country_of_interest=Country.SOUTH_AFRICA,
            work_type=WorkType.FORMAL_SECTOR_WAGED_EMPLOYMENT,
            location="Cape Town",
            timeline=given_timeline,
            questions_and_answers=given_qa,
        )

        # THEN the overview generator received all pre-linking experience context
        overview_kwargs = given_overview_generator.execute.await_args.kwargs
        assert overview_kwargs == {
            "experience_title": "Baker",
            "company_name": "Bakery",
            "work_type": WorkType.FORMAL_SECTOR_WAGED_EMPLOYMENT,
            "location": "Cape Town",
            "timeline": given_timeline,
            "country_of_interest": Country.SOUTH_AFRICA,
            "responsibilities": ["I bake bread", "I sell pastries"],
            "questions_and_answers": given_qa,
        }
        # AND the classifier received the overview combined with the formalized responsibilities
        assert given_client.classify_v2.await_args.kwargs["description"] == (
            f"{given_overview}\n\nResponsibilities:\n- Prepare artisan bread dough\n- Handle retail pastry sales"
        )
        # AND the reranker received the same overview with the ORIGINAL user responsibilities
        assert given_reranker.rerank.await_args.kwargs["overview"] == given_overview
        assert given_reranker.rerank.await_args.kwargs["responsibilities"] == ["I bake bread", "I sell pastries"]
        # AND the LLM stats from overview generation are returned in the response
        assert actual_response.llm_stats == given_stats

    @pytest.mark.asyncio
    async def test_falls_back_to_responsibilities_when_overview_generation_fails(self):
        # GIVEN an overview generator that raises an exception
        given_overview_generator = MagicMock(spec=ExperienceOverviewGenerator)
        given_overview_generator.execute = AsyncMock(side_effect=RuntimeError("LLM failed"))
        given_client = _given_v2_client()
        given_reranker = MagicMock(spec=SkillReranker)
        given_reranker.rerank = AsyncMock(side_effect=lambda **kwargs: kwargs["candidates"][:1])

        linker = ClassifierSkillLinker(
            version=ClassifierApiVersion.V2,
            client=given_client,
            reranker=given_reranker,
            overview_generator=given_overview_generator,
        )

        # WHEN the linker is executed
        actual_response = await _execute(linker)

        # THEN classification and reranking still succeed without an overview
        assert given_client.classify_v2.await_args.kwargs["description"] == "- I bake bread\n- I sell pastries"
        assert given_reranker.rerank.await_args.kwargs["overview"] is None
        assert [skill.UUID for skill in actual_response.top_skills] == ["a"]


def _associated_skill(uuid: str, relation_type: str) -> AssociatedSkillEntity:
    return AssociatedSkillEntity(
        id=uuid,
        UUID=uuid,
        preferredLabel=f"skill-{uuid}",
        altLabels=[],
        description="",
        skillType="skill/competence",
        relationType=relation_type,
        score=0.0,
    )


def _occupation_skill_entity(code: str, label: str, skills: list[AssociatedSkillEntity]) -> OccupationSkillEntity:
    return OccupationSkillEntity(
        occupation=OccupationEntity(
            id=code, UUID=code, preferredLabel=label, altLabels=[], description="", code=code, score=1.0
        ),
        associated_skills=skills,
    )


class TestExecuteWithOccupationExpansion:
    @pytest.mark.asyncio
    async def test_expands_matched_occupations_with_essential_skills_first(self):
        # GIVEN a classifier response with 1 direct skill ("a") and 2 matched occupations (one with code, one without)
        given_client = MagicMock(spec=ClassifierClient)
        given_client.classify_v2 = AsyncMock(return_value=ClassifierV2Response.model_validate({"entities": [
            _entity("skill", [_match("skill", "a", 0.9)]),
            _entity("occupation", [{
                "entity_type": "occupation",
                "similarity_score": 0.95,
                "entity": {"uuid": "occ1", "preferred_label": "baker", "esco_code": "7512.1"},
            }]),
            _entity("occupation", [{
                "entity_type": "occupation",
                "similarity_score": 0.80,
                "entity": {"uuid": "occ2", "preferred_label": "pastry chef", "esco_code": None},
            }]),
        ]}))

        # AND an occupation skill search service returning essential and optional skills (including duplicate "a")
        given_occ_service = MagicMock(spec=OccupationSkillSearchService)
        given_occ_service.get_by_esco_code = AsyncMock(return_value=[
            _occupation_skill_entity("7512.1", "baker", [
                _associated_skill("opt1", "optional"),
                _associated_skill("ess1", "essential"),
                _associated_skill("a", "essential"),
            ])
        ])
        given_occ_service.search = AsyncMock(return_value=[
            _occupation_skill_entity("7512.2", "pastry chef", [
                _associated_skill("ess2", "essential"),
            ])
        ])

        given_reranker = MagicMock(spec=SkillReranker)
        given_reranker.rerank = AsyncMock(side_effect=lambda **kwargs: kwargs["candidates"][:2])

        linker = ClassifierSkillLinker(
            version=ClassifierApiVersion.V2,
            client=given_client,
            occupation_skill_search_service=given_occ_service,
            reranker=given_reranker,
        )

        # WHEN the linker is executed
        await _execute(linker)

        # THEN get_by_esco_code was used for the coded occupation and search for the uncoded one
        given_occ_service.get_by_esco_code.assert_awaited_once_with(code="7512.1")
        given_occ_service.search.assert_awaited_once_with(query="pastry chef", k=1)
        # AND the reranker received direct skill "a" first, then essential occupation skills, then optional
        actual_candidate_uuids = [s.UUID for s in given_reranker.rerank.await_args.kwargs["candidates"]]
        assert actual_candidate_uuids == ["a", "ess1", "ess2", "opt1"]

    @pytest.mark.asyncio
    async def test_degrades_gracefully_when_occupation_expansion_fails(self):
        # GIVEN an occupation skill search service that raises an exception
        given_client = MagicMock(spec=ClassifierClient)
        given_client.classify_v2 = AsyncMock(return_value=ClassifierV2Response.model_validate({"entities": [
            _entity("skill", [_match("skill", "a", 0.9)]),
            _entity("occupation", [{
                "entity_type": "occupation",
                "similarity_score": 0.95,
                "entity": {"uuid": "occ1", "preferred_label": "baker", "esco_code": "7512.1"},
            }]),
        ]}))
        given_occ_service = MagicMock(spec=OccupationSkillSearchService)
        given_occ_service.get_by_esco_code = AsyncMock(side_effect=RuntimeError("db down"))

        linker = ClassifierSkillLinker(
            version=ClassifierApiVersion.V2,
            client=given_client,
            occupation_skill_search_service=given_occ_service,
        )

        # WHEN the linker is executed
        actual_response = await _execute(linker)

        # THEN direct classifier skills are still returned
        assert [skill.UUID for skill in actual_response.top_skills] == ["a"]
