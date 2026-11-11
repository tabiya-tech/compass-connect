import logging
from typing import Optional

from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.reranker.client import LlmRerankerClient, RerankCandidate
from app.vector_search.esco_entities import SkillEntity
from common_libs.observability.tracing import traced_observation, update_observation


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
                     max_skills: int) -> list[SkillEntity]:
        """
        :param candidates: The candidate skills, unique by UUID.
        :return: The candidates the experience shows, best first, at most max_skills. Can be empty.
        :raises LlmRerankerServiceError: if the reranker request fails.
        """
        with traced_observation(
                name="llm_skill_reranker",
                as_type="tool",
                input={"experience_title": experience_title,
                       "candidates": [skill.preferredLabel for skill in candidates]},
        ) as observation:
            response = await self._client.rank_skills(
                title=experience_title,
                company=company_name,
                work_type=work_type.value if work_type else None,
                responsibilities=responsibilities,
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
