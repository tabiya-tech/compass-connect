import os

from common_libs.llm.generative_models import GeminiGenerativeLLM
from common_libs.llm.local_llm import LocalOpenAICompatibleLLM, LocalLLMConfig
from common_libs.llm.anthropic_llm import AnthropicLLM, AnthropicLLMConfig
from common_libs.llm.models_utils import LLM, LLMConfig

_USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "").lower() in ("1", "true", "yes")
_USE_CLAUDE_API = os.getenv("USE_CLAUDE_API", "").lower() in ("1", "true", "yes")


def get_llm(*,
            system_instructions: list[str] | str | None = None,
            config: LLMConfig = LLMConfig()) -> LLM:
    """
    Returns an LLM instance based on environment:
      - USE_CLAUDE_API=true  → AnthropicLLM (requires ANTHROPIC_API_KEY)
      - USE_LOCAL_LLM=true   → LocalOpenAICompatibleLLM (ollama/llama.cpp)
      - default              → GeminiGenerativeLLM (Vertex AI)
    """
    if _USE_CLAUDE_API:
        anthropic_config = AnthropicLLMConfig(
            generation_config={
                k: v for k, v in config.generation_config.items()
                if k in ("temperature", "top_p", "max_tokens", "response_mime_type")
            }
        )
        return AnthropicLLM(
            system_instructions=system_instructions,
            config=anthropic_config,
        )

    if _USE_LOCAL_LLM:
        local_config = LocalLLMConfig(
            generation_config=dict(config.generation_config)
        )
        return LocalOpenAICompatibleLLM(
            system_instructions=system_instructions,
            config=local_config,
        )

    return GeminiGenerativeLLM(
        system_instructions=system_instructions,
        config=config,
    )
