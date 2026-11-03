from pydantic import BaseModel

from app.agent.agent_types import LLMStats
from app.vector_search.esco_entities import SkillEntity


class SkillsLinkingToolOutput(BaseModel):
    """
    The response of the SkillsLinkingTool.
    """
    top_skills: list[SkillEntity]
    llm_stats: list[LLMStats]
