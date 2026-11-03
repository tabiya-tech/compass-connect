from pydantic import BaseModel

from app.agent.agent_types import LLMStats
from app.vector_search.esco_entities import SkillEntity


class PickTopSkillsToolOutput(BaseModel):
    picked_skills: list[SkillEntity]
    remaining_skills: list[SkillEntity]
    llm_stats: list[LLMStats]
