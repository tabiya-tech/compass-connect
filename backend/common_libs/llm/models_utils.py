import logging
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Type

from dotenv import load_dotenv
from google.genai.types import GroundingMetadata
from pydantic import BaseModel

from app.agent.config import GEMINI_DEFAULT_MODELS, ModelTier
from common_libs.observability.tracing import traced_observation, update_observation
from common_libs.retry import RetryConfigWithExponentialBackOff, DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF, Retry

if TYPE_CHECKING:
    from app.app_config import LLMProvider

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# The default Vertex AI location of the generative-AI client.
# Embeddings use a separate region (VERTEX_API_EMBEDDINGS_REGION) — see GoogleEmbeddingService.

DEFAULT_VERTEX_API_GEN_AI_REGION = os.getenv("VERTEX_API_GEN_AI_REGION")
if not DEFAULT_VERTEX_API_GEN_AI_REGION:
    logging.warning("VERTEX_API_GEN_AI_REGION is not set. Using 'us-central1' as the default region.")
    DEFAULT_VERTEX_API_GEN_AI_REGION = "us-central1"
else:
    logging.info("Default Vertex AI gen-AI region is %s", DEFAULT_VERTEX_API_GEN_AI_REGION)

DEFAULT_GENERATION_CONFIG = {
    "temperature": 0.1,
    "top_p": 0.95,
}

ZERO_TEMPERATURE_GENERATION_CONFIG = {
    "temperature": 0.0,
    "top_p": 0.95,
}

LOW_TEMPERATURE_GENERATION_CONFIG = {
    "temperature": 0.1,
    "top_p": 0.95,
}

MODERATE_TEMPERATURE_GENERATION_CONFIG = {
    "temperature": 0.25,
    "top_p": 0.95,
}

MEDIUM_TEMPERATURE_GENERATION_CONFIG = {
    "temperature": 0.5,
    "top_p": 0.95,
}

HIGH_TEMPERATURE_GENERATION_CONFIG = {
    "temperature": 1.0,
    "top_p": 0.95,
}

CRAZY_TEMPERATURE_GENERATION_CONFIG = {
    "temperature": 2.0,
    "top_p": 0.95,
}

JSON_GENERATION_CONFIG = {
    "response_mime_type": "application/json",
}

_HARM_CATEGORIES = ("dangerous_content", "sexually_explicit", "harassment", "hate_speech")
"""The harm categories of the google-genai Interactions API safety settings."""

# Todo(apostolos): Specify the safety settings after we have some relevant tests
DEFAULT_SAFETY_SETTINGS: tuple[dict[str, str], ...] = tuple(
    {"type": category, "threshold": "block_only_high"} for category in _HARM_CATEGORIES)

SAFETY_OFF_SETTINGS: tuple[dict[str, str], ...] = tuple(
    {"type": category, "threshold": "block_none"} for category in _HARM_CATEGORIES)


def get_config_variation(
        start_temperature: float,
        end_temperature: float,
        start_top_p: float,
        end_top_p: float,
        attempt: int,
        max_retries: int
) -> dict:
    """
    Exponentially change temperature and top_p over retry attempts.
    The temperature and top_p are adjusted using a soft exponential curve to control the randomness and
    diversity of the model's responses.

    Typical is to start with a low temperature and top_p, and increase them with each retry attempt if the previous attempt failed.
    This allows the model to start with more focused responses and gradually increase the randomness and diversity.

    :param start_temperature: The starting temperature.
    :param end_temperature: The ending temperature.
    :param start_top_p: The starting top_p value.
    :param end_top_p: The ending top_p value.
    :param attempt: The current retry attempt.
    :param max_retries: The maximum number of retries.
    """
    progress = (attempt - 1) / max(max_retries - 1, 1)  # Normalize to [0, 1]
    exponent = 2  # Adjust curve steepness, 2 offer a soft exponential increase for 3–4 retries
    factor = progress ** exponent

    # Change temperature progressively to adjust randomness on each retry.
    # A soft exponential curve is used to smoothly transition between the starting and ending values,
    # helping control the level of diversity in the model’s responses across retries.
    temperature = round(start_temperature + (end_temperature - start_temperature) * factor, 2)

    # Adjust top_p progressively to control the range of tokens the LLM considers on each retry.
    # This gradual change helps balance variability and coherence, depending on how start and end are configured.
    # A soft exponential curve works well for 3–4 retries to shift the sampling behavior meaningfully but smoothly.
    top_p = round(start_top_p + (end_top_p - start_top_p) * factor, 2)

    return {
        "temperature": temperature,
        "top_p": top_p,
        }


_NON_GEMINI_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "ollama": "qwen2.5:7b",
}
"""
The model used for every tier of a non-Gemini provider when no tier's environment variable is set.
"""

_NON_GEMINI_FALLBACK_TIERS: dict[ModelTier, list[ModelTier]] = {
    ModelTier.DEFAULT: [],
    ModelTier.REASONING: [ModelTier.DEFAULT],
    ModelTier.DEEP_REASONING: [ModelTier.REASONING, ModelTier.DEFAULT],
}
"""
For a non-Gemini provider, the tiers whose model is used, in order, when a tier's environment variable is not set.
"""


def resolve_model_name(*, tier: ModelTier, provider: "LLMProvider") -> str:
    """
    Resolve the model name to use for a tier of a provider, in order:
      1. The tier's environment variable (LLM_DEFAULT_MODEL, LLM_REASONING_MODEL, LLM_DEEP_REASONING_MODEL).
      2. For non-Gemini providers only, the environment variable of the next tier down that is set
         (deep reasoning -> reasoning -> default).
      3. The provider's built-in default for the tier.

    The environment variables only apply when `provider` is the configured LLM_PROVIDER, so that
    Gemini-only call sites never get a model name meant for another provider.

    Reads ApplicationConfig at call time so that tests can swap config without reimporting this module.
    When the ApplicationConfig is not set (e.g. scripts, unit tests), the built-in defaults are used.
    """
    from app.app_config import get_application_config

    try:
        app_config = get_application_config()
    except RuntimeError:
        app_config = None

    if app_config is not None and app_config.llm_provider == provider:
        configured_models = {
            ModelTier.DEFAULT: app_config.llm_default_model,
            ModelTier.REASONING: app_config.llm_reasoning_model,
            ModelTier.DEEP_REASONING: app_config.llm_deep_reasoning_model,
        }
        # Gemini falls back to its own 2.5 default for the tier rather than to another tier's model.
        tiers_to_try = [tier] if provider == "gemini" else [tier, *_NON_GEMINI_FALLBACK_TIERS[tier]]
        for candidate_tier in tiers_to_try:
            if configured_models[candidate_tier]:
                return configured_models[candidate_tier]

    if provider == "gemini":
        return GEMINI_DEFAULT_MODELS[tier]
    return _NON_GEMINI_DEFAULT_MODELS[provider]


class LLMConfig(BaseModel):
    """
    Configuration for the LLM.
    """
    model_tier: ModelTier = ModelTier.DEFAULT
    """
    The capability tier of the model to use. The model name is resolved from it when the LLM is created,
    see `resolve_model_name`.
    """
    language_model_name: str | None = None
    """
    An explicit, provider-specific model name. When set, it is used as-is instead of resolving `model_tier`.
    """
    location: str = DEFAULT_VERTEX_API_GEN_AI_REGION
    generation_config: dict = DEFAULT_GENERATION_CONFIG
    """
    The generation parameters (temperature, top_p, max_output_tokens, ...). It may also carry the structured output
    of the response, see `common_libs.llm.schema_builder.with_response_schema`.
    """
    safety_settings: tuple[dict[str, str], ...] = DEFAULT_SAFETY_SETTINGS
    retry_config: RetryConfigWithExponentialBackOff = DEFAULT_RETRY_CONFIG_WITH_EXP_BACKOFF

    class Config:
        """
        Configuration settings for the LLMConfig model.
        """
        arbitrary_types_allowed = True
        """
        Allow arbitrary types, as the generation_config may carry the pydantic class of the response schema.
        """
        protected_namespaces = ()
        """
        Allow the model_tier field, which would otherwise clash with pydantic's reserved "model_" prefix.
        """


class LLMTurn(BaseModel):
    """
    A conversation turn to be used by the LLM
    """
    content: str
    role: str


class LLMInput(BaseModel):
    """
    Input for the LLM.
    """
    turns: list[LLMTurn]


class LLMResponse(BaseModel):
    """
    Response from the LLM.
    """
    text: str
    """The generated text."""
    prompt_token_count: int
    """The number of tokens in the prompt."""
    response_token_count: int
    """The number of tokens in the response."""
    grounding_metadata: GroundingMetadata | None = None
    """Grounding metadata from Google Search or other retrieval tools, when present."""


class LLM(ABC):
    """
    An abstract class for a LLM.
    """

    @abstractmethod
    async def generate_content(self, llm_input: LLMInput | str,
                               response_schema: Type[BaseModel] | None = None) -> LLMResponse:
        """
        Generate a response for the input, with retry logic with exponential backoff.
        :param llm_input: Either a LLMInput object for chat, or a string for general generative content.
        :param response_schema: The pydantic model the response must follow (structured output).
            When omitted, the response schema of the LLM's generation config is used, if any.
        :return: The generated response as a "model".
        """
        raise NotImplementedError()


def get_response_schema(generation_config: dict, response_schema: Type[BaseModel] | None = None) -> Type[BaseModel] | None:
    """
    Get the pydantic model of the structured output: the one given for the call, else the one of the generation config.
    """
    if response_schema is not None:
        return response_schema
    return generation_config.get("response_schema")


_TRACEABLE_GENERATION_PARAMETERS = ("temperature", "top_p", "max_output_tokens", "seed", "stop_sequences")
"""The generation parameters reported to the tracing backend."""


def llm_input_to_traceable(llm_input: LLMInput | str) -> str | list[dict]:
    """
    Render an LLM input as something a trace payload can carry.

    :param llm_input: The input to the LLM.
    :return: The raw string, or the turns as a list of role/content dicts.
    """
    if isinstance(llm_input, str):
        return llm_input
    return [{"role": turn.role, "content": turn.content} for turn in llm_input.turns]


class BasicLLM(LLM):
    def __init__(self, *, config: LLMConfig = LLMConfig()):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._retry_config = config.retry_config
        self._resource_name = ""
        self._model_name = config.language_model_name or resolve_model_name(tier=config.model_tier,
                                                                             provider="gemini")
        # A copy, as the callers may adjust it between attempts (see `generation_config`).
        self._generation_config = dict(config.generation_config)

    @property
    def generation_config(self) -> dict:
        """
        The generation parameters used for every call. It is read at call time, so a caller can adjust it between
        attempts, e.g. to raise the temperature to escape a repetition trap.
        """
        return self._generation_config

    async def generate_content(self, llm_input: LLMInput | str,
                               response_schema: Type[BaseModel] | None = None) -> LLMResponse:
        async def _generate_content() -> LLMResponse:
            try:
                logger.debug("Generating content with resource:%s",
                             self._resource_name)

                return await self.internal_generate_content(llm_input, response_schema)

            except Exception as e:
                logger.error("An error occurred while generating content with resource:%s",
                             self._resource_name, exc_info=True)
                raise e

        # This is the single funnel for nearly every LLM call in the backend, which is why the
        # generation observation lives here rather than in each of the ~40 call sites.
        with traced_observation(
                name=f"{self.__class__.__name__}.generate_content",
                as_type="generation",
                input=llm_input_to_traceable(llm_input),
                model=self._model_name,
                model_parameters={key: value for key, value in self._generation_config.items()
                                  if key in _TRACEABLE_GENERATION_PARAMETERS},
                metadata={"resource_name": self._resource_name},
        ) as generation:
            try:
                response = await Retry[str].call_with_exponential_backoff(callback=_generate_content, logger=logger)
            except Exception as e:
                update_observation(generation, level="ERROR", status_message=str(e))
                raise

            update_observation(
                generation,
                output=response.text,
                usage_details={
                    "input": response.prompt_token_count,
                    "output": response.response_token_count,
                    "total": response.prompt_token_count + response.response_token_count,
                },
            )
            return response

    @abstractmethod
    async def internal_generate_content(self, llm_input: LLMInput | str,
                                        response_schema: Type[BaseModel] | None = None) -> LLMResponse:
        raise NotImplementedError()
