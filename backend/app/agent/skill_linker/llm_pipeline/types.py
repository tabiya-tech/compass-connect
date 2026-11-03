from pydantic import BaseModel

from app.agent.agent_types import LLMStats
from app.vector_search.esco_entities import SkillEntity, OccupationSkillEntity


class ClusterPipelineResult(BaseModel):
    responsibilities_cluster_name: str
    responsibilities: list[str]
    contextual_titles: list[str]
    esco_occupations: list[OccupationSkillEntity]
    skills: list[SkillEntity]
    llm_stats: list[LLMStats]

    class Config:
        extra = "forbid"


class ExperiencePipelineResponse(BaseModel):
    top_skills: list[SkillEntity]
    remaining_skills: list[SkillEntity]
    llm_stats: list[LLMStats]
    cluster_results: list[ClusterPipelineResult]

    class Config:
        extra = "forbid"
