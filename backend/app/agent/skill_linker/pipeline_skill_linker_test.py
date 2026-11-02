from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.agent_types import LLMStats
from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.linking_and_ranking_pipeline import ExperiencePipelineConfig, ExperiencePipelineResponse
from app.agent.skill_linker.linking_and_ranking_pipeline.experience_pipeline import ClusterPipelineResult
from app.agent.skill_linker.pipeline_skill_linker import PipelineSkillLinker
from app.countries import Country
from app.vector_search.esco_entities import OccupationEntity, OccupationSkillEntity, SkillEntity


def _skill(uuid: str) -> SkillEntity:
    return SkillEntity(id=uuid, UUID=uuid, preferredLabel=uuid, altLabels=[], description="", skillType="knowledge",
                       score=0.0)


def _occupation(label: str) -> OccupationSkillEntity:
    return OccupationSkillEntity(
        occupation=OccupationEntity(id=label, UUID=label, preferredLabel=label, altLabels=[], description="",
                                    code="1234", score=0.0),
        associated_skills=[])


class TestPipelineSkillLinker:
    @pytest.mark.asyncio
    async def test_adapts_pipeline_response(self):
        # GIVEN a pipeline that returns skills and two clusters
        given_llm_stats = [LLMStats(prompt_token_count=1, response_token_count=1, response_time_in_sec=0.1)]
        given_pipeline_response = ExperiencePipelineResponse(
            top_skills=[_skill("top")],
            remaining_skills=[_skill("remaining")],
            llm_stats=given_llm_stats,
            cluster_results=[
                ClusterPipelineResult(responsibilities_cluster_name="c1", responsibilities=[],
                                      contextual_titles=["title 1"], esco_occupations=[_occupation("occupation 1")],
                                      skills=[], llm_stats=[]),
                ClusterPipelineResult(responsibilities_cluster_name="c2", responsibilities=[],
                                      contextual_titles=["title 2"], esco_occupations=[],
                                      skills=[], llm_stats=[]),
            ]
        )
        with patch("app.agent.skill_linker.pipeline_skill_linker.ExperiencePipeline") as mock_pipeline_class:
            mock_pipeline_class.return_value.execute = AsyncMock(return_value=given_pipeline_response)
            linker = PipelineSkillLinker(config=ExperiencePipelineConfig(), search_services=MagicMock())

            # WHEN the linker is executed
            actual_response = await linker.execute(experience_title="Baker", responsibilities=["bake"],
                                                   company_name=None, country_of_interest=Country.UNSPECIFIED,
                                                   work_type=WorkType.FORMAL_SECTOR_WAGED_EMPLOYMENT)

        # THEN the skills and llm stats of the pipeline are returned
        assert [skill.UUID for skill in actual_response.top_skills] == ["top"]
        assert [skill.UUID for skill in actual_response.remaining_skills] == ["remaining"]
        assert actual_response.llm_stats == given_llm_stats
        # AND the title candidates are the contextual titles and occupations of each cluster, in order
        assert actual_response.title_candidates == ["title 1", "occupation 1", "title 2"]
