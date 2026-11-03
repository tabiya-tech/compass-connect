import logging

from app.agent.skill_linker.classifier import ClassifierClient
from app.agent.skill_linker.classifier.linker import ClassifierSkillLinker
from app.agent.skill_linker.llm_pipeline import ExperiencePipelineConfig, PipelineSkillLinker
from app.agent.skill_linker.config import SkillLinkerType
from app.agent.skill_linker.linker import ISkillLinker
from app.app_config import ApplicationConfig
from app.vector_search.vector_search_dependencies import SearchServices

logger = logging.getLogger(__name__)


def get_skill_linker(*,
                     application_config: ApplicationConfig,
                     search_services: SearchServices,
                     experience_pipeline_config: ExperiencePipelineConfig) -> ISkillLinker:
    """
    Create the skill linker selected by the application configuration
    (BACKEND_SKILL_LINKER, and CLASSIFIER_API_VERSION for the classifier).
    """
    if application_config.skill_linker == SkillLinkerType.CLASSIFIER:
        return ClassifierSkillLinker(
            version=application_config.classifier_api_version,
            client=ClassifierClient(base_url=application_config.classifier_api_url,
                                    api_key=application_config.classifier_api_key),
            skill_search_service=search_services.skill_search_service
        )

    return PipelineSkillLinker(config=experience_pipeline_config, search_services=search_services)
