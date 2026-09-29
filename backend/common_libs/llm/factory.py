import logging

from common_libs.llm.models_utils import LLM, LLMConfig, resolve_model_name

logger = logging.getLogger(__name__)


def get_llm(*,
            system_instructions: list[str] | str | None = None,
            config: LLMConfig = LLMConfig()) -> LLM:
    """
    Return an LLM instance for the provider configured in ApplicationConfig.

    Provider is set via LLM_PROVIDER env var (gemini | anthropic | ollama).
    The model name is resolved from config.model_tier (see resolve_model_name),
    unless config.language_model_name is set explicitly.

    Reads ApplicationConfig at call time so that tests can swap config without
    reimporting this module.
    """
    from app.app_config import get_application_config
    from common_libs.llm.generative_models import GeminiGenerativeLLM
    from common_libs.llm.anthropic_llm import AnthropicLLM, AnthropicLLMConfig
    from common_libs.llm.local_llm import LocalOpenAICompatibleLLM, LocalLLMConfig

    app_config = get_application_config()
    provider = app_config.llm_provider

    if provider == "anthropic":
        # Map Gemini-specific generation_config keys to what AnthropicLLM understands.
        # max_output_tokens (Gemini name) → max_tokens (Anthropic name).
        gen = config.generation_config
        anthropic_gen = {
            k: v for k, v in gen.items()
            if k in ("temperature", "top_p", "response_mime_type", "response_schema")
        }
        anthropic_gen["max_tokens"] = (
            gen.get("max_tokens")
            or gen.get("max_output_tokens")
            or 4096
        )
        anthropic_config = AnthropicLLMConfig(
            language_model_name=config.language_model_name or resolve_model_name(tier=config.model_tier,
                                                                                 provider="anthropic"),
            generation_config=anthropic_gen,
        )
        return AnthropicLLM(
            system_instructions=system_instructions,
            config=anthropic_config,
            api_key=app_config.anthropic_api_key,
        )

    if provider == "ollama":
        local_config = LocalLLMConfig(
            language_model_name=config.language_model_name or resolve_model_name(tier=config.model_tier,
                                                                                 provider="ollama"),
            base_url=app_config.ollama_base_url,
            generation_config=dict(config.generation_config),
        )
        return LocalOpenAICompatibleLLM(
            system_instructions=system_instructions,
            config=local_config,
        )

    # Default: Gemini / Vertex AI. The model name is resolved by BasicLLM.
    return GeminiGenerativeLLM(
        system_instructions=system_instructions,
        config=config,
    )
