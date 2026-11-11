import json
import logging
from typing import Optional

from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.classifier.adapters import ClassifierAdapterV1, ClassifierAdapterV2, \
    IClassifierAdapter
from app.agent.skill_linker.classifier.config import ClassifierSkillLinkerConfig
from app.agent.skill_linker.classifier.client import ClassifierApiVersion, ClassifierClient, ClassifierServiceError
from app.agent.skill_linker.classifier.skill_ranking import SkillCandidate, deduplicate_candidates, rank_skills
from app.agent.skill_linker.linker import ISkillLinker, SkillLinkerResponse
from app.agent.skill_linker.reranker import LlmRerankerServiceError, SkillReranker
from app.countries import Country
from app.vector_search.esco_entities import SkillEntity
from app.vector_search.esco_search_service import SkillSearchService
from common_libs.observability.tracing import traced_observation, update_observation


class ClassifierSkillLinker(ISkillLinker):
    """
    Skill linker backed by the Tabiya classifier API, which extracts entities (skills, occupations) from the
    experience and links them to the taxonomy in a single call.

    The API version specific work is delegated to an adapter (see ClassifierAdapterV1 and ClassifierAdapterV2),
    the candidates it returns are then ranked into the top and remaining skills (see rank_skills).

    If a reranker is given, the best scoring candidates are reranked by an LLM, and the skills it picks are the
    top skills. If the reranker fails or picks nothing, the classifier ranking is kept.
    """

    def __init__(self, *,
                 version: ClassifierApiVersion,
                 client: ClassifierClient,
                 skill_search_service: Optional[SkillSearchService] = None,
                 config: Optional[ClassifierSkillLinkerConfig] = None,
                 reranker: Optional[SkillReranker] = None):
        self._version = version
        self._config = config or ClassifierSkillLinkerConfig()
        self._reranker = reranker
        self._adapter = _create_adapter(version=version, client=client,
                                        skill_search_service=skill_search_service, config=self._config)
        self._logger = logging.getLogger(self.__class__.__name__)

    async def execute(self, *,
                      experience_title: str,
                      responsibilities: list[str],
                      company_name: Optional[str],
                      country_of_interest: Country,
                      work_type: WorkType) -> SkillLinkerResponse:
        with traced_observation(
                name="classifier_skill_linker",
                as_type="chain",
                input={"experience_title": experience_title, "responsibilities": responsibilities},
                metadata={"version": self._version.value, "reranked": self._reranker is not None},
        ) as observation:
            try:
                matches = await self._adapter.classify(experience_title=experience_title,
                                                       responsibilities=responsibilities)
            except ClassifierServiceError as e:
                # Do not break the conversation if the classifier is unavailable, behave like a linker that found nothing.
                self._logger.error("Failed to link skills for experience title: '%s'. Error: %s",
                                   experience_title, e, exc_info=e)
                return SkillLinkerResponse(top_skills=[], remaining_skills=[])

            top_skills, remaining_skills = rank_skills(matches.skill_candidates,
                                                       number_of_top_skills=self._config.number_of_top_skills)
            if self._reranker is not None and matches.skill_candidates:
                reranked = await self._rerank(experience_title=experience_title,
                                              responsibilities=responsibilities,
                                              company_name=company_name,
                                              work_type=work_type,
                                              candidates=matches.skill_candidates)
                if reranked is not None:
                    top_skills, remaining_skills = reranked
            response = SkillLinkerResponse(top_skills=top_skills,
                                           remaining_skills=remaining_skills,
                                           title_candidates=matches.title_candidates)
            update_observation(observation, output={
                "top_skills": [skill.preferredLabel for skill in response.top_skills],
                "remaining_skills_count": len(response.remaining_skills),
            })
            if self._logger.isEnabledFor(logging.INFO):
                self._logger.info("Classifier (%s) linked experience '%s' to top skills: %s",
                                  self._version.value, experience_title,
                                  json.dumps([skill.preferredLabel for skill in response.top_skills], ensure_ascii=False))
            return response

    async def _rerank(self, *,
                      experience_title: str,
                      responsibilities: list[str],
                      company_name: Optional[str],
                      work_type: WorkType,
                      candidates: list[SkillCandidate]) -> Optional[tuple[list[SkillEntity], list[SkillEntity]]]:
        """
        Rerank the best scoring candidates with the LLM reranker.

        :return: (top_skills, remaining_skills), or None to keep the classifier ranking.
        """
        by_score = [candidate.skill for candidate in deduplicate_candidates(candidates)]
        try:
            top_skills = await self._reranker.rerank(experience_title=experience_title,
                                                     responsibilities=responsibilities,
                                                     company_name=company_name,
                                                     work_type=work_type,
                                                     candidates=by_score[:self._config.max_rerank_candidates],
                                                     max_skills=self._config.number_of_top_skills)
        except LlmRerankerServiceError as e:
            # Do not break the conversation if the reranker is unavailable, keep the classifier ranking.
            self._logger.warning("Failed to rerank the skills of experience title: '%s', keeping the classifier "
                                 "ranking. Error: %s", experience_title, e, exc_info=e)
            return None
        if not top_skills:
            self._logger.warning("The reranker picked no skills for experience title: '%s', keeping the classifier "
                                 "ranking.", experience_title)
            return None
        top_skills_uuids = {skill.UUID for skill in top_skills}
        return top_skills, [skill for skill in by_score if skill.UUID not in top_skills_uuids]


def _create_adapter(*,
                    version: ClassifierApiVersion,
                    client: ClassifierClient,
                    skill_search_service: Optional[SkillSearchService],
                    config: ClassifierSkillLinkerConfig) -> IClassifierAdapter:
    if version == ClassifierApiVersion.V2:
        return ClassifierAdapterV2(client=client, config=config)
    if version == ClassifierApiVersion.V1:
        if skill_search_service is None:
            raise ValueError("The classifier v1 skill linker requires a skill search service to resolve the matched labels")
        return ClassifierAdapterV1(client=client, config=config, skill_search_service=skill_search_service)
    raise ValueError(f"ClassifierSkillLinker does not support the classifier API version: {version}")
