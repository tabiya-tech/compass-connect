import logging

from app.agent.skill_linker.classifier import ClassifierClient
from app.agent.skill_linker.classifier.linker import ClassifierSkillLinker
from app.agent.skill_linker.llm_pipeline import ExperiencePipelineConfig, PipelineSkillLinker
from app.agent.skill_linker.config import SkillLinkerType
from app.agent.skill_linker.linker import ISkillLinker
from app.agent.skill_linker.reranker import GoogleIdTokenProvider, LlmRerankerClient, SkillReranker
from app.app_config import ApplicationConfig
from app.vector_search.vector_search_dependencies import SearchServices

logger = logging.getLogger(__name__)


def get_skill_linker(*,
                     application_config: ApplicationConfig,
                     search_services: SearchServices,
                     experience_pipeline_config: ExperiencePipelineConfig) -> ISkillLinker:
    """
    Create the skill linker selected by the application configuration
    (BACKEND_SKILL_LINKER, and CLASSIFIER_API_VERSION and LLM_RERANKER_URL for the classifier).
    """
    if application_config.skill_linker == SkillLinkerType.CLASSIFIER:
        return ClassifierSkillLinker(
            version=application_config.classifier_api_version,
            client=ClassifierClient(base_url=application_config.classifier_api_url,
                                    api_key=application_config.classifier_api_key),
            skill_search_service=search_services.skill_search_service,
            reranker=_get_skill_reranker(application_config.llm_reranker_url)
        )

    return PipelineSkillLinker(config=experience_pipeline_config, search_services=search_services)


_token_providers: dict[str, GoogleIdTokenProvider] = {}


def _get_skill_reranker(llm_reranker_url: str | None) -> SkillReranker | None:
    if not llm_reranker_url:
        return None
    # The linker is created per request, share the token provider so that its ID token cache outlives the request.
    token_provider = _token_providers.get(llm_reranker_url)
    if token_provider is None:
        token_provider = _token_providers[llm_reranker_url] = GoogleIdTokenProvider(audience=llm_reranker_url)
    return SkillReranker(client=LlmRerankerClient(base_url=llm_reranker_url, token_provider=token_provider))
