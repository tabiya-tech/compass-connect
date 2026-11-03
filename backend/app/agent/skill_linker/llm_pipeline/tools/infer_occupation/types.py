from pydantic import BaseModel

from app.agent.agent_types import LLMStats
from app.vector_search.esco_entities import OccupationSkillEntity


class InferOccupationToolOutput(BaseModel):
    contextual_titles: list[str]
    esco_occupations: list[OccupationSkillEntity]
    responsibilities: list[str]
    llm_stats: list[LLMStats]

    class Config:
        extra = "forbid"
