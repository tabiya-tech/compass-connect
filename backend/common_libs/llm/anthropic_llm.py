import json
import logging
import os

import anthropic
from pydantic import BaseModel

from common_libs.llm.models_utils import LLM, LLMInput, LLMResponse
from common_libs.retry import RetryConfigWithExponentialBackOff, DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF, Retry

_STRUCTURED_OUTPUT_TOOL_NAME = "structured_output"


def _normalize_schema(node):
    """Convert Vertex AI schema format (type_/format_/nullable) to standard JSON Schema.

    Vertex AI uses type_="ARRAY" + nullable=True for Optional[list[...]].
    Standard JSON Schema expresses this as type=["array","null"] or just omits the
    field from `required`. Since optional fields are already absent from `required`,
    we drop `nullable` and leave the type as-is — models handle missing optional
    fields correctly when they're not in `required`.
    """
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "type_":
                # type_ can be a proto enum int or a string; normalise to lowercase string.
                out["type"] = v.lower() if isinstance(v, str) else str(v).lower()
            elif k == "format_":
                out["format"] = v
            elif k == "nullable":
                pass  # already expressed by absence from `required`
            else:
                out[k] = _normalize_schema(v)
        return out
    elif isinstance(node, list):
        return [_normalize_schema(i) for i in node]
    return node


class AnthropicLLMConfig(BaseModel):
    language_model_name: str = "claude-sonnet-4-6"
    generation_config: dict = {"temperature": 0.1, "max_tokens": 4096}
    retry_config: RetryConfigWithExponentialBackOff = DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF

    class Config:
        arbitrary_types_allowed = True


class AnthropicLLM(LLM):
    """
    Wraps the Anthropic Claude API.

    Extends LLM directly rather than BasicLLM to avoid triggering vertexai.init().

    Structured output: when the caller's generation config includes response_schema
    (Gemini's structured output field), this class uses Anthropic tool use with
    tool_choice forced to that tool — the API-level equivalent of Gemini's response_schema.

    JSON mode without schema: when response_mime_type is "application/json" but no
    response_schema is present, a system prompt instruction is used instead.
    """

    def __init__(self, *,
                 system_instructions: list[str] | str | None = None,
                 config: AnthropicLLMConfig = AnthropicLLMConfig(),
                 api_key: str | None = None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._model_name = config.language_model_name
        self._generation_config = dict(config.generation_config)
        self._system_instructions = system_instructions
        self._json_mode = config.generation_config.get("response_mime_type") == "application/json"
        self._response_schema = config.generation_config.get("response_schema")
        self._retry_config = config.retry_config
        # Create the client once; reuse across all calls from this instance.
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ["ANTHROPIC_API_KEY"]
        )

    async def generate_content(self, llm_input: LLMInput | str) -> LLMResponse:
        async def _call() -> LLMResponse:
            return await self._internal_generate_content(llm_input)

        return await Retry[str].call_with_exponential_backoff(callback=_call, logger=self.logger)

    async def _internal_generate_content(self, llm_input: LLMInput | str) -> LLMResponse:
        system = self._build_system()
        messages = self._build_messages(llm_input)

        kwargs: dict = {
            "model": self._model_name,
            "messages": messages,
            "max_tokens": self._generation_config.get("max_tokens", 4096),
        }
        if system:
            kwargs["system"] = system

        # temperature and top_p are top-level kwargs in the Anthropic SDK.
        # The two cannot coexist; prefer temperature.
        if "temperature" in self._generation_config:
            kwargs["temperature"] = self._generation_config["temperature"]
        elif "top_p" in self._generation_config:
            kwargs["top_p"] = self._generation_config["top_p"]

        if self._json_mode and self._response_schema:
            # Use tool use to enforce the response schema at the API level.
            # tool_choice "tool" forces the model to call exactly this tool,
            # giving the same guarantee as Gemini's response_schema.
            normalized = _normalize_schema(self._response_schema)
            kwargs["tools"] = [{
                "name": _STRUCTURED_OUTPUT_TOOL_NAME,
                "description": "Return a structured response conforming to the required schema.",
                "input_schema": normalized,
            }]
            kwargs["tool_choice"] = {"type": "tool", "name": _STRUCTURED_OUTPUT_TOOL_NAME}

        response = await self._client.messages.create(**kwargs)

        if self._json_mode and self._response_schema:
            # Extract the tool call input dict and re-serialize as JSON string
            # so the rest of the codebase can parse it as before.
            tool_block = next(
                (b for b in response.content if b.type == "tool_use"),
                None,
            )
            if tool_block is None:
                raise ValueError("Anthropic returned no tool_use block despite forced tool_choice")
            # If the schema requires a "message" field and it came back empty, retry —
            # same signal as an empty response from a text model.
            if isinstance(tool_block.input, dict) and tool_block.input.get("message") == "":
                raise ValueError("Anthropic tool response contained an empty 'message' field")
            text = json.dumps(tool_block.input)
        else:
            text = self._strip_markdown_fences(response.content[0].text)

        return LLMResponse(
            text=text,
            prompt_token_count=response.usage.input_tokens,
            response_token_count=response.usage.output_tokens,
            grounding_metadata=None,
        )

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            text = text[text.index("\n") + 1:] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        return text.strip()

    def _build_system(self) -> str:
        parts = []
        if self._system_instructions:
            if isinstance(self._system_instructions, str):
                parts.append(self._system_instructions)
            else:
                parts.extend(self._system_instructions)
        if self._json_mode and not self._response_schema:
            parts.append("You must respond with valid JSON only. Do not include any text outside the JSON object.")
        return "\n".join(parts)

    def _build_messages(self, llm_input: LLMInput | str) -> list[dict]:
        if isinstance(llm_input, str):
            return [{"role": "user", "content": llm_input}]

        messages = []
        for turn in llm_input.turns:
            if not turn.content:
                # Anthropic rejects turns with empty content — skip and log so it's traceable.
                self.logger.debug("Skipping empty-content turn with role=%s", turn.role)
                continue
            # Compass uses "model" for assistant turns; Anthropic uses "assistant"
            role = "assistant" if turn.role == "model" else turn.role
            messages.append({"role": role, "content": turn.content})
        return messages
