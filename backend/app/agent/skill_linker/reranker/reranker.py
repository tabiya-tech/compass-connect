import logging
from typing import Optional

from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.reranker.client import LlmRerankerClient, RerankCandidate
from app.vector_search.esco_entities import SkillEntity
from common_libs.observability.tracing import traced_observation, update_observation


def _embed_overview(*,
                    overview: str,
                    company: Optional[str],
                    work_type: Optional[str],
                    responsibilities: list[str]) -> tuple[Optional[str], Optional[str], list[str]]:
    """
    The reranker API has no overview field. Its prompt shows the experience as `Company: ...` and
    `Work type: ...` lines followed by the `Responsibilities:` bullets, so an overview appended to the last of
    those fields after a line break becomes its own `Overview: ...` line, just before the responsibilities.
    The model then reads it as background, while a responsibility would count as evidence for a skill.
    Falls back to a first responsibility when neither field is set.

    :return: The company, work type and responsibilities to send.
    """
    overview_line = "Overview: " + " ".join(overview.split())  # keep the overview on a single line
    if work_type and work_type.strip():
        return company, f"{work_type.strip()}\n{overview_line}", responsibilities
    if company and company.strip():
        return f"{company.strip()}\n{overview_line}", work_type, responsibilities
    return company, work_type, [overview_line, *responsibilities]


class SkillReranker:
    """
    Reranks the candidate skills of an experience with the LLM reranker: the LLM picks the candidates the
    experience shows, best first.
    """

    def __init__(self, *, client: LlmRerankerClient):
        self._client = client
        self._logger = logging.getLogger(self.__class__.__name__)

    async def rerank(self, *,
                     experience_title: str,
                     responsibilities: list[str],
                     company_name: Optional[str],
                     work_type: Optional[WorkType],
                     candidates: list[SkillEntity],
                     max_skills: int,
                     overview: Optional[str] = None) -> list[SkillEntity]:
        """
        :param candidates: The candidate skills, unique by UUID.
        :return: The candidates the experience shows, best first, at most max_skills. Can be empty.
        :raises LlmRerankerServiceError: if the reranker request fails.
        """
        cleaned_overview = (overview or "").strip()
        rerank_company = company_name
        rerank_work_type = work_type.value if work_type else None
        rerank_responsibilities = responsibilities
        if cleaned_overview:
            rerank_company, rerank_work_type, rerank_responsibilities = _embed_overview(
                overview=cleaned_overview,
                company=company_name,
                work_type=rerank_work_type,
                responsibilities=responsibilities)
        observation_input: dict = {
            "experience_title": experience_title,
            "candidates": [skill.preferredLabel for skill in candidates],
        }
        if cleaned_overview:
            observation_input["overview"] = cleaned_overview
        with traced_observation(
                name="llm_skill_reranker",
                as_type="tool",
                input=observation_input,
        ) as observation:
            response = await self._client.rank_skills(
                title=experience_title,
                company=rerank_company,
                work_type=rerank_work_type,
                responsibilities=rerank_responsibilities,
                candidates=[RerankCandidate(id=skill.UUID,
                                            label=skill.preferredLabel,
                                            description=skill.description,
                                            score=skill.score) for skill in candidates],
                max_skills=max_skills)
            skills_by_uuid = {skill.UUID: skill for skill in candidates}
            # The reranker only returns ids it was given, ignore any other defensively.
            ranked = [skills_by_uuid[uuid] for uuid in response.ranked_ids if uuid in skills_by_uuid][:max_skills]
            update_observation(observation, output={
                "ranked_skills": [skill.preferredLabel for skill in ranked],
                "model": response.model,
                "timings": response.timings,
            })
            return ranked
