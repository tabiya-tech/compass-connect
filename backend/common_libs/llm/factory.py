import os

from common_libs.llm.generative_models import GeminiGenerativeLLM
from common_libs.llm.local_llm import LocalOpenAICompatibleLLM, LocalLLMConfig
from common_libs.llm.models_utils import LLM, LLMConfig

_USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "").lower() in ("1", "true", "yes")


def get_llm(*,
            system_instructions: list[str] | str | None = None,
            config: LLMConfig = LLMConfig()) -> LLM:
    """
    Return a GeminiGenerativeLLM by default, or a LocalOpenAICompatibleLLM when
    USE_LOCAL_LLM=true is set in the environment.

    The local LLM talks to any OpenAI-compatible endpoint (ollama, llama.cpp, etc.)
    configured via LOCAL_LLM_BASE_URL and LOCAL_LLM_MODEL_NAME.

    The generation_config passed via LLMConfig is forwarded to the local model
    for the keys it understands (temperature, top_p, max_tokens, frequency_penalty).
    Vertex-specific keys (candidate_count, response_mime_type, response_schema) are
    silently ignored by the local LLM.
    """
    if _USE_LOCAL_LLM:
        local_config = LocalLLMConfig(
            generation_config={
                k: v for k, v in config.generation_config.items()
                if k in ("temperature", "top_p", "max_tokens", "frequency_penalty")
            }
        )
        return LocalOpenAICompatibleLLM(
            system_instructions=system_instructions,
            config=local_config,
        )

    return GeminiGenerativeLLM(
        system_instructions=system_instructions,
        config=config,
    )
