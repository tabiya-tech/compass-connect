from typing import Optional

from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.linking_and_ranking_pipeline import ExperiencePipeline, ExperiencePipelineConfig
from app.agent.skill_linker.skill_linker import ISkillLinker, SkillLinkerResponse
from app.countries import Country
from app.vector_search.vector_search_dependencies import SearchServices


class PipelineSkillLinker(ISkillLinker):
    """
    Skill linker backed by the LLM based linking and ranking pipeline.
    """

    def __init__(self, *, config: ExperiencePipelineConfig, search_services: SearchServices):
        self._pipeline = ExperiencePipeline(config=config, search_services=search_services)

    async def execute(self, *,
                      experience_title: str,
                      responsibilities: list[str],
                      company_name: Optional[str],
                      country_of_interest: Country,
                      work_type: WorkType) -> SkillLinkerResponse:
        pipeline_result = await self._pipeline.execute(
            experience_title=experience_title,
            responsibilities=responsibilities,
            company_name=company_name,
            country_of_interest=country_of_interest,
            work_type=work_type
        )

        title_candidates: list[str] = []
        for cluster_result in pipeline_result.cluster_results:
            title_candidates.extend(cluster_result.contextual_titles)
            title_candidates.extend(
                occupation_skill.occupation.preferredLabel for occupation_skill in cluster_result.esco_occupations)

        return SkillLinkerResponse(
            top_skills=pipeline_result.top_skills,
            remaining_skills=pipeline_result.remaining_skills,
            title_candidates=title_candidates,
            llm_stats=pipeline_result.llm_stats
        )
