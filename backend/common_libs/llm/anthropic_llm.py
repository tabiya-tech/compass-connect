import json
import logging
import os
from typing import Type

import anthropic
from pydantic import BaseModel

from common_libs.llm.models_utils import LLM, LLMInput, LLMResponse, get_response_schema
from common_libs.retry import RetryConfigWithExponentialBackOff, DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF, Retry

_STRUCTURED_OUTPUT_TOOL_NAME = "structured_output"


def _json_schema_for_tool(response_schema: Type[BaseModel]) -> dict:
    """
    The JSON schema of the pydantic class, with the references to its definitions ($defs) inlined,
    as the input schema of the structured output tool.
    """
    schema = response_schema.model_json_schema()
    definitions = schema.pop("$defs", {})

    def _inline(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return _inline(definitions[node["$ref"].split("/")[-1]])
            return {key: _inline(value) for key, value in node.items()}
        if isinstance(node, list):
            return [_inline(item) for item in node]
        return node

    return _inline(schema)


class AnthropicLLMConfig(BaseModel):
    language_model_name: str = "claude-sonnet-4-6"
    generation_config: dict = {"temperature": 0.1, "max_tokens": 4096}
    retry_config: RetryConfigWithExponentialBackOff = DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF

    class Config:
        arbitrary_types_allowed = True


class AnthropicLLM(LLM):
    """
    Wraps the Anthropic Claude API.

    Structured output: when a response schema is given for the call, or the caller's generation config
    includes one (see `with_response_schema`), this class uses Anthropic tool use with
    tool_choice forced to that tool — the API-level equivalent of Gemini's structured output.

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
        self._retry_config = config.retry_config
        # Create the client once; reuse across all calls from this instance.
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ["ANTHROPIC_API_KEY"]
        )

    @property
    def generation_config(self) -> dict:
        """The generation parameters, read at call time."""
        return self._generation_config

    async def generate_content(self, llm_input: LLMInput | str,
                               response_schema: Type[BaseModel] | None = None) -> LLMResponse:
        async def _call() -> LLMResponse:
            return await self._internal_generate_content(llm_input, get_response_schema(self._generation_config, response_schema))

        return await Retry[str].call_with_exponential_backoff(callback=_call, logger=self.logger)

    async def _internal_generate_content(self, llm_input: LLMInput | str,
                                         response_schema: Type[BaseModel] | None) -> LLMResponse:
        system = self._build_system(json_without_schema=self._json_mode and response_schema is None)
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

        if response_schema is not None:
            # Use tool use to enforce the response schema at the API level.
            # tool_choice "tool" forces the model to call exactly this tool,
            # giving the same guarantee as Gemini's structured output.
            kwargs["tools"] = [{
                "name": _STRUCTURED_OUTPUT_TOOL_NAME,
                "description": "Return a structured response conforming to the required schema.",
                "input_schema": _json_schema_for_tool(response_schema),
            }]
            kwargs["tool_choice"] = {"type": "tool", "name": _STRUCTURED_OUTPUT_TOOL_NAME}

        response = await self._client.messages.create(**kwargs)

        if response_schema is not None:
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

    def _build_system(self, *, json_without_schema: bool) -> str:
        parts = []
        if self._system_instructions:
            if isinstance(self._system_instructions, str):
                parts.append(self._system_instructions)
            else:
                parts.extend(self._system_instructions)
        if json_without_schema:
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
