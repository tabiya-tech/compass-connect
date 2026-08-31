import logging
import os

import httpx
from pydantic import BaseModel

from common_libs.llm.models_utils import LLM, LLMInput, LLMResponse
from common_libs.retry import RetryConfigWithExponentialBackOff, DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF, Retry

_USE_THINKING = os.getenv("LOCAL_LLM_THINK", "").lower() in ("1", "true", "yes")


class LocalLLMConfig(BaseModel):
    language_model_name: str = "qwen2.5:7b"
    base_url: str = "http://localhost:11434"
    generation_config: dict = {"temperature": 0.1, "top_p": 0.95, "max_tokens": 4096}
    retry_config: RetryConfigWithExponentialBackOff = DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF

    class Config:
        arbitrary_types_allowed = True


class LocalOpenAICompatibleLLM(LLM):
    """
    Wraps a locally-running model via the native ollama /api/chat endpoint.

    Uses ollama's native API (not /v1/chat/completions) so that think:false
    is respected, disabling qwen3's slow chain-of-thought reasoning mode.

    Extends LLM directly rather than BasicLLM to avoid triggering vertexai.init().
    Does not include traced_observation tracing.
    """

    def __init__(self, *,
                 system_instructions: list[str] | str | None = None,
                 config: LocalLLMConfig = LocalLLMConfig()):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._retry_config = config.retry_config
        self._base_url = config.base_url
        self._model_name = config.language_model_name
        self._generation_config = dict(config.generation_config)
        self._system_instructions = system_instructions
        self._resource_name = f"{config.base_url}/api/chat"

    async def generate_content(self, llm_input: LLMInput | str) -> LLMResponse:
        async def _call() -> LLMResponse:
            return await self._internal_generate_content(llm_input)

        return await Retry[str].call_with_exponential_backoff(callback=_call, logger=self.logger)

    async def _internal_generate_content(self, llm_input: LLMInput | str) -> LLMResponse:
        messages = self._build_messages(llm_input)
        options = {k: v for k, v in self._generation_config.items()
                   if k in ("temperature", "top_p", "num_predict", "frequency_penalty")}
        # ollama uses num_predict instead of max_tokens
        if "max_tokens" in self._generation_config and "num_predict" not in options:
            options["num_predict"] = self._generation_config["max_tokens"]

        payload = {
            "model": self._model_name,
            "messages": messages,
            "stream": False,
            "think": _USE_THINKING,
            "options": options,
        }
        # Gemini uses response_mime_type:"application/json" to enforce JSON output;
        # ollama uses a top-level "format":"json" field for the same purpose.
        if self._generation_config.get("response_mime_type") == "application/json":
            payload["format"] = "json"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._resource_name,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=300.0,
            )
            response.raise_for_status()
            data = response.json()

        text = data["message"]["content"]
        return LLMResponse(
            text=text,
            prompt_token_count=data.get("prompt_eval_count", 0),
            response_token_count=data.get("eval_count", 0),
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
                # Compass uses "model" for assistant turns; ollama uses "assistant"
                role = "assistant" if turn.role == "model" else turn.role
                messages.append({"role": role, "content": turn.content})
        return messages
