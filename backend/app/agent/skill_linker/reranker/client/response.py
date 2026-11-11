"""
Response schema of the LLM reranker /rank/skills endpoint.
"""
from pydantic import BaseModel, Field


class RerankSkillsResponse(BaseModel):
    ranked_ids: list[str]
    """
    The ids of the skills the experience shows, best first, at most `max_skills`.
    """

    discarded_ids: list[str] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
    model: str = ""
