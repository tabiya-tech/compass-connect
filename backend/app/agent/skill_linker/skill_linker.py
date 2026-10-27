from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field

from app.agent.agent_types import LLMStats
from app.agent.experience.work_type import WorkType
from app.countries import Country
from app.vector_search.esco_entities import SkillEntity


class SkillLinkerResponse(BaseModel):
    """
    The result of linking an experience to skills, independent of the linker implementation.
    """

    top_skills: list[SkillEntity]
    """
    The most relevant skills of the experience, in order of relevance.
    """

    remaining_skills: list[SkillEntity]
    """
    Other skills linked to the experience that did not make it to the top skills.
    """

    title_candidates: list[str] = Field(default_factory=list)
    """
    Candidate titles (e.g. contextual titles, occupation labels) for normalizing the experience title,
    in order of preference.
    """

    llm_stats: list[LLMStats] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class ISkillLinker(ABC):
    """
    Links an experience (title, responsibilities, ...) to skills of the taxonomy.
    """

    @abstractmethod
    async def execute(self, *,
                      experience_title: str,
                      responsibilities: list[str],
                      company_name: Optional[str],
                      country_of_interest: Country,
                      work_type: WorkType) -> SkillLinkerResponse:
        raise NotImplementedError()
