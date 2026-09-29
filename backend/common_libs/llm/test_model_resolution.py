from typing import Optional
from unittest.mock import patch

import pytest

from app.agent.config import ModelTier
from app.app_config import ApplicationConfig, set_application_config
from common_libs.llm.factory import get_llm
from common_libs.llm.generative_models import GeminiGenerativeLLM
from common_libs.llm.models_utils import LLMConfig, resolve_model_name


def _set_llm_config(config: ApplicationConfig, *,
                    provider: str,
                    default_model: Optional[str] = None,
                    reasoning_model: Optional[str] = None,
                    deep_reasoning_model: Optional[str] = None) -> None:
    set_application_config(config.model_copy(update={
        "llm_provider": provider,
        "llm_default_model": default_model,
        "llm_reasoning_model": reasoning_model,
        "llm_deep_reasoning_model": deep_reasoning_model,
        "anthropic_api_key": "foo",
    }))


class TestResolveModelName:
    @pytest.mark.parametrize("given_tier, expected_model", [
        (ModelTier.DEFAULT, "gemini-2.5-flash-lite"),
        (ModelTier.REASONING, "gemini-2.5-flash"),
        (ModelTier.DEEP_REASONING, "gemini-2.5-pro"),
    ])
    def test_gemini_uses_gemini_2_5_defaults_when_no_model_is_set(self, setup_application_config,
                                                                  given_tier: ModelTier, expected_model: str):
        # GIVEN the gemini provider is configured without any tier models
        _set_llm_config(setup_application_config, provider="gemini")

        # WHEN the model name for the given tier is resolved
        actual_model = resolve_model_name(tier=given_tier, provider="gemini")

        # THEN expect the gemini 2.5 default for the tier
        assert actual_model == expected_model

    @pytest.mark.parametrize("given_tier, expected_model", [
        (ModelTier.DEFAULT, "given-default"),
        (ModelTier.REASONING, "given-reasoning"),
        (ModelTier.DEEP_REASONING, "given-deep-reasoning"),
    ])
    @pytest.mark.parametrize("given_provider", ["gemini", "anthropic", "ollama"])
    def test_uses_the_tier_model_when_it_is_set(self, setup_application_config,
                                                given_provider: str, given_tier: ModelTier, expected_model: str):
        # GIVEN the provider is configured with a model for every tier
        _set_llm_config(setup_application_config, provider=given_provider,
                        default_model="given-default",
                        reasoning_model="given-reasoning",
                        deep_reasoning_model="given-deep-reasoning")

        # WHEN the model name for the given tier is resolved
        actual_model = resolve_model_name(tier=given_tier, provider=given_provider)

        # THEN expect the model configured for the tier
        assert actual_model == expected_model

    @pytest.mark.parametrize("given_reasoning_model, given_tier, expected_model", [
        (None, ModelTier.REASONING, "gemini-2.5-flash"),
        (None, ModelTier.DEEP_REASONING, "gemini-2.5-pro"),
        ("given-reasoning", ModelTier.DEEP_REASONING, "gemini-2.5-pro"),
    ])
    def test_gemini_does_not_fall_back_to_another_tier(self, setup_application_config,
                                                       given_reasoning_model: Optional[str],
                                                       given_tier: ModelTier, expected_model: str):
        # GIVEN the gemini provider is configured with a default model, and maybe a reasoning model
        _set_llm_config(setup_application_config, provider="gemini",
                        default_model="given-default",
                        reasoning_model=given_reasoning_model)

        # WHEN the model name for a tier without a model is resolved
        actual_model = resolve_model_name(tier=given_tier, provider="gemini")

        # THEN expect the gemini 2.5 default for the tier, not another tier's model
        assert actual_model == expected_model

    @pytest.mark.parametrize("given_tier", list(ModelTier))
    @pytest.mark.parametrize("given_provider, expected_model", [
        ("anthropic", "claude-sonnet-4-6"),
        ("ollama", "qwen2.5:7b"),
    ])
    def test_non_gemini_uses_the_provider_default_when_no_model_is_set(self, setup_application_config,
                                                                       given_provider: str, expected_model: str,
                                                                       given_tier: ModelTier):
        # GIVEN a non-gemini provider is configured without any tier models
        _set_llm_config(setup_application_config, provider=given_provider)

        # WHEN the model name for the given tier is resolved
        actual_model = resolve_model_name(tier=given_tier, provider=given_provider)

        # THEN expect the provider default
        assert actual_model == expected_model

    @pytest.mark.parametrize("given_default_model, given_reasoning_model, given_tier, expected_model", [
        # only the default model is set: every tier uses it
        ("given-default", None, ModelTier.DEFAULT, "given-default"),
        ("given-default", None, ModelTier.REASONING, "given-default"),
        ("given-default", None, ModelTier.DEEP_REASONING, "given-default"),
        # the default and reasoning models are set: deep reasoning uses the reasoning model
        ("given-default", "given-reasoning", ModelTier.DEFAULT, "given-default"),
        ("given-default", "given-reasoning", ModelTier.REASONING, "given-reasoning"),
        ("given-default", "given-reasoning", ModelTier.DEEP_REASONING, "given-reasoning"),
        # only the reasoning model is set: deep reasoning uses it, default uses the provider default
        (None, "given-reasoning", ModelTier.REASONING, "given-reasoning"),
        (None, "given-reasoning", ModelTier.DEEP_REASONING, "given-reasoning"),
    ])
    @pytest.mark.parametrize("given_provider", ["anthropic", "ollama"])
    def test_non_gemini_falls_back_to_the_next_tier_down(self, setup_application_config,
                                                         given_provider: str,
                                                         given_default_model: Optional[str],
                                                         given_reasoning_model: Optional[str],
                                                         given_tier: ModelTier, expected_model: str):
        # GIVEN a non-gemini provider is configured without a deep reasoning model
        _set_llm_config(setup_application_config, provider=given_provider,
                        default_model=given_default_model,
                        reasoning_model=given_reasoning_model)

        # WHEN the model name for the given tier is resolved
        actual_model = resolve_model_name(tier=given_tier, provider=given_provider)

        # THEN expect the tier model when set, otherwise the model of the next tier down that is set
        assert actual_model == expected_model

    @pytest.mark.parametrize("given_provider, expected_model", [
        ("anthropic", "claude-sonnet-4-6"),
        ("ollama", "qwen2.5:7b"),
    ])
    def test_non_gemini_default_tier_does_not_fall_back_to_a_higher_tier(self, setup_application_config,
                                                                         given_provider: str, expected_model: str):
        # GIVEN a non-gemini provider is configured with only a reasoning model
        _set_llm_config(setup_application_config, provider=given_provider, reasoning_model="given-reasoning")

        # WHEN the model name for the default tier is resolved
        actual_model = resolve_model_name(tier=ModelTier.DEFAULT, provider=given_provider)

        # THEN expect the provider default, not the reasoning model
        assert actual_model == expected_model

    @pytest.mark.parametrize("given_tier, expected_model", [
        (ModelTier.DEFAULT, "gemini-2.5-flash-lite"),
        (ModelTier.REASONING, "gemini-2.5-flash"),
        (ModelTier.DEEP_REASONING, "gemini-2.5-pro"),
    ])
    def test_ignores_the_models_of_another_provider(self, setup_application_config,
                                                    given_tier: ModelTier, expected_model: str):
        # GIVEN the anthropic provider is configured with a model for every tier
        _set_llm_config(setup_application_config, provider="anthropic",
                        default_model="given-default",
                        reasoning_model="given-reasoning",
                        deep_reasoning_model="given-deep-reasoning")

        # WHEN the model name for the given tier is resolved for gemini (e.g. a gemini-only call site)
        actual_model = resolve_model_name(tier=given_tier, provider="gemini")

        # THEN expect the gemini 2.5 default for the tier
        assert actual_model == expected_model

    @pytest.mark.parametrize("given_tier, expected_model", [
        (ModelTier.DEFAULT, "gemini-2.5-flash-lite"),
        (ModelTier.REASONING, "gemini-2.5-flash"),
        (ModelTier.DEEP_REASONING, "gemini-2.5-pro"),
    ])
    def test_uses_the_defaults_when_the_application_config_is_not_set(self, given_tier: ModelTier,
                                                                      expected_model: str):
        # GIVEN the application config is not set
        set_application_config(None)

        # WHEN the model name for the given tier is resolved
        actual_model = resolve_model_name(tier=given_tier, provider="gemini")

        # THEN expect the gemini 2.5 default for the tier
        assert actual_model == expected_model


class TestGetLLM:
    @pytest.mark.parametrize("given_provider, given_llm_class", [
        ("anthropic", "common_libs.llm.anthropic_llm.AnthropicLLM"),
        ("ollama", "common_libs.llm.local_llm.LocalOpenAICompatibleLLM"),
    ])
    def test_non_gemini_llm_gets_the_model_of_the_tier(self, setup_application_config,
                                                       given_provider: str, given_llm_class: str):
        # GIVEN a non-gemini provider is configured with a reasoning model
        _set_llm_config(setup_application_config, provider=given_provider,
                        default_model="given-default",
                        reasoning_model="given-reasoning")

        # WHEN an llm is requested for the reasoning tier
        with patch(given_llm_class) as mock_llm_class:
            get_llm(config=LLMConfig(model_tier=ModelTier.REASONING))

        # THEN expect the llm to be created with the reasoning model
        assert mock_llm_class.call_args.kwargs["config"].language_model_name == "given-reasoning"

    def test_explicit_model_name_is_used_as_is(self, setup_application_config):
        # GIVEN the anthropic provider is configured with a reasoning model
        _set_llm_config(setup_application_config, provider="anthropic", reasoning_model="given-reasoning")
        # AND an llm config with an explicit model name
        given_config = LLMConfig(model_tier=ModelTier.REASONING, language_model_name="given-explicit-model")

        # WHEN an llm is requested for the config
        with patch("common_libs.llm.anthropic_llm.AnthropicLLM") as mock_llm_class:
            get_llm(config=given_config)

        # THEN expect the llm to be created with the explicit model name
        assert mock_llm_class.call_args.kwargs["config"].language_model_name == "given-explicit-model"


class TestGeminiGenerativeLLM:
    @pytest.mark.parametrize("given_config, expected_model", [
        (LLMConfig(), "gemini-2.5-flash-lite"),
        (LLMConfig(model_tier=ModelTier.DEEP_REASONING), "given-deep-reasoning"),
        (LLMConfig(model_tier=ModelTier.DEEP_REASONING, language_model_name="given-explicit-model"),
         "given-explicit-model"),
    ])
    def test_gemini_model_is_resolved_on_creation(self, setup_application_config,
                                                  given_config: LLMConfig, expected_model: str):
        # GIVEN the gemini provider is configured with only a deep reasoning model
        _set_llm_config(setup_application_config, provider="gemini", deep_reasoning_model="given-deep-reasoning")

        # WHEN a gemini llm is created for the given config
        with patch("common_libs.llm.models_utils._init_once"), \
                patch("common_libs.llm.generative_models.GenerativeModel") as mock_generative_model:
            actual_llm = GeminiGenerativeLLM(config=given_config)

        # THEN expect the underlying model to be created with the resolved model name
        assert mock_generative_model.call_args.kwargs["model_name"] == expected_model
        # AND the llm to report the same model name (used for tracing)
        # noinspection PyProtectedMember
        assert actual_llm._model_name == expected_model  # pylint: disable=protected-access
