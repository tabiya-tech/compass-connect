import json
import logging
from typing import Optional

from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.classifier.adapters import ClassifierAdapterV1, ClassifierAdapterV2, \
    IClassifierAdapter
from app.agent.skill_linker.classifier.config import ClassifierSkillLinkerConfig
from app.agent.skill_linker.classifier.client import ClassifierApiVersion, ClassifierClient, ClassifierServiceError
from app.agent.skill_linker.classifier.skill_ranking import rank_skills
from app.agent.skill_linker.linker import ISkillLinker, SkillLinkerResponse
from app.countries import Country
from app.vector_search.esco_search_service import SkillSearchService
from common_libs.observability.tracing import traced_observation, update_observation


class ClassifierSkillLinker(ISkillLinker):
    """
    Skill linker backed by the Tabiya classifier API, which extracts entities (skills, occupations) from the
    experience and links them to the taxonomy in a single call.

    The API version specific work is delegated to an adapter (see ClassifierAdapterV1 and ClassifierAdapterV2),
    the candidates it returns are then ranked into the top and remaining skills (see rank_skills).
    """

    def __init__(self, *,
                 version: ClassifierApiVersion,
                 client: ClassifierClient,
                 skill_search_service: Optional[SkillSearchService] = None,
                 config: Optional[ClassifierSkillLinkerConfig] = None):
        self._version = version
        self._config = config or ClassifierSkillLinkerConfig()
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
                metadata={"version": self._version.value},
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
