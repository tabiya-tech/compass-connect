import logging

from app.agent.skill_linker.classifier import ClassifierClient, ClassifierSkillLinker
from app.agent.skill_linker.llm_pipeline import ExperiencePipelineConfig, PipelineSkillLinker
from app.agent.skill_linker.linker import ISkillLinker
from app.app_config import ApplicationConfig
from app.vector_search.vector_search_dependencies import SearchServices

logger = logging.getLogger(__name__)


def get_skill_linker(*,
                     application_config: ApplicationConfig,
                     search_services: SearchServices,
                     experience_pipeline_config: ExperiencePipelineConfig) -> ISkillLinker:
    """
    Create the skill linker selected by the application configuration (BACKEND_SKILL_LINKER).
    """
    skill_linker_type = application_config.skill_linker
    if skill_linker_type.is_classifier:
        return ClassifierSkillLinker(
            version=skill_linker_type,
            client=ClassifierClient(base_url=application_config.classifier_api_url,
                                    api_key=application_config.classifier_api_key),
            skill_search_service=search_services.skill_search_service
        )

    return PipelineSkillLinker(config=experience_pipeline_config, search_services=search_services)
