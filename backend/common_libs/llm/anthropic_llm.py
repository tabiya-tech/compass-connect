import logging
import os

from pydantic import BaseModel

from common_libs.llm.models_utils import LLM, LLMInput, LLMResponse
from common_libs.retry import RetryConfigWithExponentialBackOff, DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF, Retry


class AnthropicLLMConfig(BaseModel):
    language_model_name: str = os.getenv("ANTHROPIC_MODEL_NAME", "claude-sonnet-4-6")
    generation_config: dict = {"temperature": 0.1, "max_tokens": 4096}
    retry_config: RetryConfigWithExponentialBackOff = DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF

    class Config:
        arbitrary_types_allowed = True


class AnthropicLLM(LLM):
    """
    Wraps the Anthropic Claude API.

    Extends LLM directly rather than BasicLLM to avoid triggering vertexai.init().
    Requires ANTHROPIC_API_KEY environment variable.

    JSON mode: when the caller's generation config includes response_mime_type:"application/json"
    (Gemini's JSON mode field), this class prepends a JSON instruction to the system prompt
    since Anthropic doesn't have a native JSON-only mode at the API level.
    """

    def __init__(self, *,
                 system_instructions: list[str] | str | None = None,
                 config: AnthropicLLMConfig = AnthropicLLMConfig()):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._retry_config = config.retry_config
        self._model_name = config.language_model_name
        self._generation_config = dict(config.generation_config)
        self._system_instructions = system_instructions
        self._json_mode = config.generation_config.get("response_mime_type") == "application/json"

    async def generate_content(self, llm_input: LLMInput | str) -> LLMResponse:
        async def _call() -> LLMResponse:
            return await self._internal_generate_content(llm_input)

        return await Retry[str].call_with_exponential_backoff(callback=_call, logger=self.logger)

    async def _internal_generate_content(self, llm_input: LLMInput | str) -> LLMResponse:
        import anthropic

        system = self._build_system()
        messages = self._build_messages(llm_input)

        kwargs = {
            "model": self._model_name,
            "messages": messages,
            "max_tokens": self._generation_config.get("max_tokens", 4096),
        }
        if system:
            kwargs["system"] = system

        temp = self._generation_config.get("temperature")
        if temp is not None:
            kwargs["temperature"] = temp

        top_p = self._generation_config.get("top_p")
        if top_p is not None:
            kwargs["top_p"] = top_p

        client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = await client.messages.create(**kwargs)

        text = response.content[0].text
        return LLMResponse(
            text=text,
            prompt_token_count=response.usage.input_tokens,
            response_token_count=response.usage.output_tokens,
            grounding_metadata=None,
        )

    def _build_system(self) -> str:
        parts = []
        if self._system_instructions:
            if isinstance(self._system_instructions, str):
                parts.append(self._system_instructions)
            else:
                parts.extend(self._system_instructions)
        if self._json_mode:
            parts.append("You must respond with valid JSON only. Do not include any text outside the JSON object.")
        return "\n".join(parts)

    def _build_messages(self, llm_input: LLMInput | str) -> list[dict]:
        if isinstance(llm_input, str):
            return [{"role": "user", "content": llm_input}]

        messages = []
        for turn in llm_input.turns:
            # Compass uses "model" for assistant turns; Anthropic uses "assistant"
            role = "assistant" if turn.role == "model" else turn.role
            messages.append({"role": role, "content": turn.content})
        return messages
