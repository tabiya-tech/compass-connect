import json

import pytest
from pydantic import ValidationError

from app.i18n.types import Locale
from app.speech_to_text.config import parse_speech_to_text_config
from app.speech_to_text.types import SpeechToTextConfig


def _given_enabled_config(**overrides) -> dict:
    config = {
        "enabled": True,
        "model": "chirp_3",
        "maxRecordingSeconds": 60,
        "maxAudioBytes": 10485760,
        "rateLimitPerMinute": 10,
        "locales": ["en-US", "sw-KE"],
    }
    config.update(overrides)
    return config


class TestParseSpeechToTextConfig:
    @pytest.mark.parametrize("given_raw", [None, "", "   "], ids=["unset", "empty", "blank"])
    def test_voice_input_is_off_when_the_variable_is_not_set(self, given_raw):
        # GIVEN the environment variable is not set
        # WHEN the settings are parsed
        actual_config = parse_speech_to_text_config(given_raw)

        # THEN expect voice input to be off
        assert actual_config.enabled is False
        # AND no locale to be needed
        assert actual_config.enabled_locales == frozenset()

    def test_parses_the_camel_case_json_into_the_settings(self):
        # GIVEN the camelCase JSON of an enabled configuration
        given_config = _given_enabled_config(maxRecordingSeconds=30, maxAudioBytes=1024, rateLimitPerMinute=3)
        given_raw = json.dumps(given_config)

        # WHEN the settings are parsed
        actual_config = parse_speech_to_text_config(given_raw)

        # THEN expect the snake_case settings to hold the configured values
        assert actual_config.enabled == given_config["enabled"]
        assert actual_config.model == given_config["model"]
        assert actual_config.max_recording_seconds == given_config["maxRecordingSeconds"]
        assert actual_config.max_audio_bytes == given_config["maxAudioBytes"]
        assert actual_config.rate_limit_per_minute == given_config["rateLimitPerMinute"]
        # AND the configured locales to be offered
        expected_locales = frozenset(Locale(locale) for locale in given_config["locales"])
        assert actual_config.enabled_locales == expected_locales
        assert all(actual_config.is_locale_enabled(locale) for locale in expected_locales)
        # AND a locale that is not configured not to be offered
        given_unconfigured_locale = Locale.ES_ES
        assert given_unconfigured_locale not in expected_locales
        assert actual_config.is_locale_enabled(given_unconfigured_locale) is False

    def test_rejects_json_that_cannot_be_parsed(self):
        # GIVEN a value that is not JSON
        given_raw = "{enabled: true"

        # WHEN the settings are parsed
        # THEN expect a ValueError naming the variable
        with pytest.raises(ValueError, match="BACKEND_SPEECH_TO_TEXT_CONFIG"):
            parse_speech_to_text_config(given_raw)


class TestSpeechToTextConfig:
    def test_the_settings_are_immutable(self):
        # GIVEN parsed settings
        given_config = SpeechToTextConfig.model_validate(_given_enabled_config())

        # WHEN a setting is changed
        # THEN expect it to be refused
        with pytest.raises(ValidationError):
            given_config.enabled = False  # type: ignore[misc]
        with pytest.raises(ValidationError):
            given_config.locales = frozenset()  # type: ignore[misc]

    def test_accepts_a_disabled_feature_without_locales(self):
        # GIVEN a disabled feature without any locale
        given_config = {"enabled": False}

        # WHEN the settings are validated
        actual_config = SpeechToTextConfig.model_validate(given_config)

        # THEN expect them to be accepted, with the feature off
        assert actual_config.enabled is False

    def test_offers_no_locale_when_the_feature_is_disabled(self):
        # GIVEN a disabled feature with an enabled locale
        given_config = _given_enabled_config(enabled=False)

        # WHEN the settings are validated
        actual_config = SpeechToTextConfig.model_validate(given_config)

        # THEN expect no locale to be offered
        assert actual_config.enabled_locales == frozenset()
        assert not any(actual_config.is_locale_enabled(Locale(locale)) for locale in given_config["locales"])

    @pytest.mark.parametrize("given_config, expected_error", [
        (_given_enabled_config(locales=[]), "has no locale"),
        (_given_enabled_config(locales=["xx-YY"]), "locales"),
        (_given_enabled_config(locales={"en-US": {"enabled": True}}), "locales"),
        (_given_enabled_config(model="chirp_2"), "model"),
        (_given_enabled_config(maxRecordingSeconds=0), "maxRecordingSeconds"),
        (_given_enabled_config(maxRecordingSeconds=61), "maxRecordingSeconds"),
        (_given_enabled_config(maxAudioBytes=0), "maxAudioBytes"),
        (_given_enabled_config(maxAudioBytes=10 * 1024 * 1024 + 1), "maxAudioBytes"),
        (_given_enabled_config(rateLimitPerMinute=0), "rateLimitPerMinute"),
        (_given_enabled_config(maxRecordingSecond=30), "maxRecordingSecond"),
    ], ids=["enabled without locales", "unknown locale", "settings per locale", "unsupported model",
            "no recording time", "recording longer than a minute", "no audio size", "audio larger than 10 MB",
            "no rate limit", "unknown key"])
    def test_rejects_invalid_settings(self, given_config, expected_error):
        # GIVEN invalid settings
        # WHEN the settings are validated
        # THEN expect a validation error that names the problem
        with pytest.raises(ValidationError, match=expected_error):
            SpeechToTextConfig.model_validate(given_config)

    def test_rejects_an_unknown_key_even_when_the_feature_is_disabled(self):
        # GIVEN a disabled feature with a typo in a key
        given_unknown_key = "maxRecordingSecond"
        given_config = {"enabled": False, given_unknown_key: 30}

        # WHEN the settings are validated
        # THEN expect a validation error that names the key
        with pytest.raises(ValidationError, match=given_unknown_key):
            SpeechToTextConfig.model_validate(given_config)
