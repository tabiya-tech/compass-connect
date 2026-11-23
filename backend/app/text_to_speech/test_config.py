import json

import pytest
from pydantic import ValidationError

from app.i18n.types import Locale
from app.text_to_speech.config import parse_text_to_speech_config
from app.text_to_speech.types import MAX_INPUT_TOKENS, MAX_STYLE_BYTES, MAX_TEXT_BYTES_LIMIT, TextToSpeechConfig

_GIVEN_STYLE = "warm, clear and friendly, at a moderate pace"


def _given_locale(**overrides) -> dict:
    locale = {"enabled": True, "voice": "Kore", "style": _GIVEN_STYLE}
    locale.update(overrides)
    return locale


def _given_enabled_config(**overrides) -> dict:
    config = {
        "enabled": True,
        "model": "gemini-3.8-flash-tts",
        "maxTextBytes": 7168,
        "rateLimitPerMinute": 20,
        "locales": {"en-US": _given_locale()},
    }
    config.update(overrides)
    return config


class TestParseTextToSpeechConfig:
    @pytest.mark.parametrize("given_raw", [None, "", "   "], ids=["unset", "empty", "blank"])
    def test_read_aloud_is_off_when_the_variable_is_not_set(self, given_raw):
        # GIVEN the environment variable is not set
        # WHEN the settings are parsed
        actual_config = parse_text_to_speech_config(given_raw)

        # THEN expect read aloud to be off
        assert actual_config.enabled is False
        # AND no locale to be needed
        assert actual_config.locales == {}
        assert actual_config.enabled_locales == frozenset()

    def test_parses_the_camel_case_json_into_the_settings(self):
        # GIVEN the camelCase JSON of an enabled configuration
        given_config = _given_enabled_config(
            model="gemini-3.8-flash-lite-tts", maxTextBytes=1000, rateLimitPerMinute=5,
            locales={"en-US": _given_locale(), "en-GB": _given_locale(enabled=False)})
        given_raw = json.dumps(given_config)

        # WHEN the settings are parsed
        actual_config = parse_text_to_speech_config(given_raw)

        # THEN expect the snake_case settings to hold the configured values
        assert actual_config.enabled == given_config["enabled"]
        assert actual_config.model == given_config["model"]
        assert actual_config.max_text_bytes == given_config["maxTextBytes"]
        assert actual_config.rate_limit_per_minute == given_config["rateLimitPerMinute"]
        # AND only the enabled locale to be offered
        assert actual_config.enabled_locales == frozenset({Locale.EN_US})
        # AND the enabled locale to resolve to its voice settings
        actual_locale = actual_config.locale_settings(Locale.EN_US)
        given_locale = given_config["locales"][Locale.EN_US.value]
        assert actual_locale.voice == given_locale["voice"]
        assert actual_locale.style == given_locale["style"]
        # AND the disabled and the missing locales to resolve to nothing
        assert actual_config.locale_settings(Locale.EN_GB) is None
        assert actual_config.locale_settings(Locale.SW_KE) is None

    def test_rejects_json_that_cannot_be_parsed(self):
        # GIVEN a value that is not JSON
        given_raw = "[not json"

        # WHEN the settings are parsed
        # THEN expect a ValueError naming the variable
        with pytest.raises(ValueError, match="BACKEND_TEXT_TO_SPEECH_CONFIG"):
            parse_text_to_speech_config(given_raw)


class TestTextToSpeechConfig:
    def test_the_settings_are_immutable(self):
        # GIVEN parsed settings
        given_config = TextToSpeechConfig.model_validate(_given_enabled_config())

        # WHEN a setting is changed
        # THEN expect it to be refused
        with pytest.raises(ValidationError):
            given_config.max_text_bytes = 10  # type: ignore[misc]
        with pytest.raises(ValidationError):
            given_config.locales[Locale.EN_US].voice = "Puck"  # type: ignore[misc]

    def test_accepts_a_disabled_feature_without_locales(self):
        # GIVEN a disabled feature without any locale
        given_config = {"enabled": False}

        # WHEN the settings are validated
        actual_config = TextToSpeechConfig.model_validate(given_config)

        # THEN expect them to be accepted, with the feature off
        assert actual_config.enabled is False

    def test_offers_no_locale_when_the_feature_is_disabled(self):
        # GIVEN a disabled feature with an enabled locale
        given_config = _given_enabled_config(enabled=False)

        # WHEN the settings are validated
        actual_config = TextToSpeechConfig.model_validate(given_config)

        # THEN expect no locale to be offered
        assert actual_config.enabled_locales == frozenset()
        assert actual_config.locale_settings(Locale.EN_US) is None

    @pytest.mark.parametrize("given_model", ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"])
    def test_accepts_both_gemini_3_8_tts_models(self, given_model):
        # GIVEN a configuration with one of the Gemini 3.8 TTS models
        given_config = _given_enabled_config(model=given_model)

        # WHEN the settings are validated
        actual_config = TextToSpeechConfig.model_validate(given_config)

        # THEN expect the model
        assert actual_config.model == given_model

    def test_defaults_to_the_gemini_3_8_flash_tts_model_and_the_longest_text(self):
        # GIVEN a configuration without a model or a text limit
        given_config = {key: value for key, value in _given_enabled_config().items()
                        if key not in ("model", "maxTextBytes")}

        # WHEN the settings are validated
        actual_config = TextToSpeechConfig.model_validate(given_config)

        # THEN expect the flash model, and the longest text
        expected_default_model = "gemini-3.8-flash-tts"
        assert actual_config.model == expected_default_model
        assert actual_config.max_text_bytes == MAX_TEXT_BYTES_LIMIT

    def test_the_longest_text_and_style_fit_within_the_input_limit_of_gemini_3_8_tts(self):
        # GIVEN the input limit of the Gemini 3.8 TTS models, in tokens, as Google documents it
        given_documented_max_input_tokens = 8192

        # THEN expect it to be the limit we apply
        assert MAX_INPUT_TOKENS == given_documented_max_input_tokens
        # AND the longest text and the longest style together, in bytes, not to exceed it, a token covering at least
        # one byte
        assert MAX_TEXT_BYTES_LIMIT + MAX_STYLE_BYTES <= given_documented_max_input_tokens

    def test_trims_the_voice_and_the_style(self):
        # GIVEN a voice and a style
        given_voice = "Kore"
        given_style = _GIVEN_STYLE
        # AND a locale where they have surrounding whitespace
        given_config = _given_enabled_config(
            locales={"en-US": _given_locale(voice=f" {given_voice} ", style=f"  {given_style}\n")})

        # WHEN the settings are validated
        actual_config = TextToSpeechConfig.model_validate(given_config)

        # THEN expect the voice and the style without the whitespace
        assert actual_config.locales[Locale.EN_US].voice == given_voice
        assert actual_config.locales[Locale.EN_US].style == given_style

    @pytest.mark.parametrize("given_config, expected_error", [
        (_given_enabled_config(locales={}), "none of its locales is enabled"),
        (_given_enabled_config(locales={"en-US": _given_locale(enabled=False)}), "none of its locales is enabled"),
        (_given_enabled_config(locales={"ny-ZM": _given_locale()}), "locales.ny-ZM"),
        (_given_enabled_config(locales={"en-US": {"enabled": True, "style": _GIVEN_STYLE}}),
         "voice"),
        (_given_enabled_config(locales={"en-US": {"enabled": True, "voice": "Kore"}}),
         "style"),
        (_given_enabled_config(locales={"en-US": _given_locale(voice="  ")}), "voice"),
        (_given_enabled_config(locales={"en-US": _given_locale(style="")}), "style"),
        (_given_enabled_config(locales={"en-US": _given_locale(style="é" * (MAX_STYLE_BYTES // 2 + 1))}),
         f"at most {MAX_STYLE_BYTES} bytes"),
        (_given_enabled_config(model="gemini-2.0-tts"), "model"),
        (_given_enabled_config(model="gemini-2.5-flash-tts"), "model"),
        (_given_enabled_config(audioEncoding="MP3"), "audioEncoding"),
        (_given_enabled_config(maxTextBytes=0), "maxTextBytes"),
        (_given_enabled_config(maxTextBytes=MAX_TEXT_BYTES_LIMIT + 1), "maxTextBytes"),
        (_given_enabled_config(rateLimitPerMinute=-1), "rateLimitPerMinute"),
        (_given_enabled_config(maxTextLenght=100), "maxTextLenght"),
    ], ids=["enabled without locales", "enabled without an enabled locale", "unknown locale",
            "missing voice", "missing style", "blank voice", "empty style",
            "style over its limit in bytes", "unsupported model", "a model before Gemini 3.8", "the removed encoding",
            "no text length", "text longer than the input limit", "negative rate limit", "unknown key"])
    def test_rejects_invalid_settings(self, given_config, expected_error):
        # GIVEN invalid settings
        # WHEN the settings are validated
        # THEN expect a validation error that names the problem
        with pytest.raises(ValidationError, match=expected_error):
            TextToSpeechConfig.model_validate(given_config)

    def test_rejects_an_invalid_locale_even_when_the_feature_is_disabled(self):
        # GIVEN a disabled feature with a locale that has no voice
        given_config = {"enabled": False, "locales": {"en-US": {"style": _GIVEN_STYLE}}}

        # WHEN the settings are validated
        # THEN expect a validation error that names the missing voice
        with pytest.raises(ValidationError, match="voice"):
            TextToSpeechConfig.model_validate(given_config)
