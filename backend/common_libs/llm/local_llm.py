import logging
import os

import httpx
from pydantic import BaseModel

from common_libs.llm.models_utils import LLM, LLMInput, LLMResponse
from common_libs.retry import RetryConfigWithExponentialBackOff, DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF, Retry


class LocalLLMConfig(BaseModel):
    language_model_name: str = os.getenv("LOCAL_LLM_MODEL_NAME", "qwen2.5:7b")
    base_url: str = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434")
    generation_config: dict = {"temperature": 0.1, "top_p": 0.95, "max_tokens": 4096}
    retry_config: RetryConfigWithExponentialBackOff = DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF

    class Config:
        arbitrary_types_allowed = True


class LocalOpenAICompatibleLLM(LLM):
    """
    Wraps a locally-running model that exposes an OpenAI-compatible
    /v1/chat/completions endpoint (ollama, llama.cpp --server, lm-studio, etc.).

    Extends LLM directly rather than BasicLLM to avoid triggering vertexai.init().
    Does not include traced_observation tracing.
    """

    def __init__(self, *,
                 system_instructions: list[str] | str | None = None,
                 config: LocalLLMConfig = LocalLLMConfig()):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._retry_config = config.retry_config
        self._resource_name = f"{config.base_url}/v1/chat/completions"
        self._base_url = config.base_url
        self._model_name = config.language_model_name
        self._generation_config = dict(config.generation_config)
        self._system_instructions = system_instructions

    async def generate_content(self, llm_input: LLMInput | str) -> LLMResponse:
        async def _call() -> LLMResponse:
            return await self._internal_generate_content(llm_input)

        return await Retry[str].call_with_exponential_backoff(callback=_call, logger=self.logger)

    async def _internal_generate_content(self, llm_input: LLMInput | str) -> LLMResponse:
        messages = self._build_messages(llm_input)
        payload = {
            "model": self._model_name,
            "messages": messages,
            **{k: v for k, v in self._generation_config.items()
               if k in ("temperature", "top_p", "max_tokens", "frequency_penalty")},
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._resource_name,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            prompt_token_count=usage.get("prompt_tokens", 0),
            response_token_count=usage.get("completion_tokens", 0),
            grounding_metadata=None,
        )

    def _build_messages(self, llm_input: LLMInput | str) -> list[dict]:
        messages = []
        if self._system_instructions:
            sys_text = (self._system_instructions
                        if isinstance(self._system_instructions, str)
                        else "\n".join(self._system_instructions))
            messages.append({"role": "system", "content": sys_text})

        if isinstance(llm_input, str):
            messages.append({"role": "user", "content": llm_input})
        else:
            for turn in llm_input.turns:
                # Compass uses "model" for assistant turns; OpenAI uses "assistant"
                role = "assistant" if turn.role == "model" else turn.role
                messages.append({"role": role, "content": turn.content})
        return messages
