import logging

import pytest

from app.i18n.types import Locale
from app.text_to_speech.adapter import ITextToSpeechAdapter
from app.text_to_speech.errors import (EmptySynthesisError, LocaleNotEnabledError, TextToSpeechAdapterError,
                                       TextToSpeechServiceError)
from app.text_to_speech.service import TextToSpeechService
from app.text_to_speech.types import TextToSpeechConfig, VoiceSettings
from app.text_to_speech.test_audio import is_mp3, make_wav
from common_libs.retry import RetryConfigWithExponentialBackOff

_GIVEN_WAV = make_wav()
""" The audio the adapter returns: a WAV file, as Gemini TTS returns it. """
_GIVEN_TEXT = "Hello, let us talk about your work experience."
_NO_WAIT_RETRY = RetryConfigWithExponentialBackOff(max_retries=3, initial_wait=0, base_backoff_factor=1, jitter=0)


class _FakeAdapter(ITextToSpeechAdapter):
    """ Answers with the given outcomes in order: audio bytes, or an exception to raise. """

    def __init__(self, *outcomes: bytes | Exception):
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, VoiceSettings]] = []

    async def synthesize(self, *, text, voice):
        self.calls.append((text, voice))
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


_GIVEN_LOCALE = Locale.EN_US
_GIVEN_VOICE = VoiceSettings(language_code=_GIVEN_LOCALE.value, voice="Kore", style="warm and calm")
""" The voice settings configured for _GIVEN_LOCALE. """
_GIVEN_DISABLED_LOCALE = Locale.EN_GB
_GIVEN_UNCONFIGURED_LOCALE = Locale.SW_KE


def _given_config() -> TextToSpeechConfig:
    return TextToSpeechConfig.model_validate({
        "enabled": True,
        "locales": {
            _GIVEN_LOCALE.value: {"enabled": True, "voice": _GIVEN_VOICE.voice, "style": _GIVEN_VOICE.style},
            _GIVEN_DISABLED_LOCALE.value: {"enabled": False, "voice": "Puck", "style": "calm"},
        },
    })


def _given_service(adapter: ITextToSpeechAdapter) -> TextToSpeechService:
    return TextToSpeechService(config=_given_config(), adapter=adapter, retry_config=_NO_WAIT_RETRY)


class TestTextToSpeechService:
    @pytest.mark.asyncio
    async def test_reads_the_text_in_the_voice_of_its_locale(self):
        # GIVEN an adapter that returns WAV audio
        given_adapter = _FakeAdapter(_GIVEN_WAV)

        # WHEN a text in an enabled locale is synthesized
        actual_audio = await _given_service(given_adapter).synthesize(text=_GIVEN_TEXT, locale=_GIVEN_LOCALE)

        # THEN expect the audio encoded to MP3, for the locale
        expected_media_type = "audio/mpeg"
        assert is_mp3(actual_audio.content)
        assert actual_audio.media_type == expected_media_type
        assert actual_audio.locale == _GIVEN_LOCALE
        # AND the adapter to have been asked once, with the voice settings of the locale
        assert given_adapter.calls == [(_GIVEN_TEXT, _GIVEN_VOICE)]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_locale", [_GIVEN_DISABLED_LOCALE, _GIVEN_UNCONFIGURED_LOCALE],
                             ids=["disabled", "not configured"])
    async def test_rejects_a_locale_without_read_aloud_without_calling_the_adapter(self, given_locale):
        # GIVEN an adapter
        given_adapter = _FakeAdapter(_GIVEN_WAV)

        # WHEN a text in a locale without read aloud is synthesized
        # THEN expect a LocaleNotEnabledError
        with pytest.raises(LocaleNotEnabledError):
            await _given_service(given_adapter).synthesize(text=_GIVEN_TEXT, locale=given_locale)
        # AND the adapter not to have been called, so no other voice reads the text
        assert given_adapter.calls == []

    @pytest.mark.asyncio
    async def test_raises_an_empty_synthesis_error_when_no_audio_is_returned(self):
        # GIVEN an adapter that returns no audio
        given_adapter = _FakeAdapter(b"")

        # WHEN a text is synthesized
        # THEN expect an EmptySynthesisError
        with pytest.raises(EmptySynthesisError):
            await _given_service(given_adapter).synthesize(text=_GIVEN_TEXT, locale=_GIVEN_LOCALE)

    @pytest.mark.asyncio
    async def test_raises_a_service_error_when_the_audio_cannot_be_encoded_to_mp3(self):
        # GIVEN an adapter that returns audio that is not a WAV file
        given_adapter = _FakeAdapter(b"not a wav file")

        # WHEN a text is synthesized
        # THEN expect a TextToSpeechServiceError, the service having sent audio that cannot be read
        with pytest.raises(TextToSpeechServiceError):
            await _given_service(given_adapter).synthesize(text=_GIVEN_TEXT, locale=_GIVEN_LOCALE)
        # AND the adapter to have been called once, as asking again would give the same audio
        assert len(given_adapter.calls) == 1

    @pytest.mark.asyncio
    async def test_retries_a_transient_failure(self):
        # GIVEN an adapter that fails once with a transient error, then returns audio
        given_adapter = _FakeAdapter(TextToSpeechAdapterError("unavailable", status_code=503), _GIVEN_WAV)

        # WHEN a text is synthesized
        actual_audio = await _given_service(given_adapter).synthesize(text=_GIVEN_TEXT, locale=_GIVEN_LOCALE)

        # THEN expect the audio, as MP3
        assert is_mp3(actual_audio.content)
        # AND the adapter to have been called twice
        assert len(given_adapter.calls) == 2

    @pytest.mark.asyncio
    async def test_gives_up_after_the_configured_attempts(self):
        # GIVEN an adapter that keeps failing with a transient error
        given_adapter = _FakeAdapter(TextToSpeechAdapterError("unavailable", status_code=503))

        # WHEN a text is synthesized
        # THEN expect a TextToSpeechServiceError
        with pytest.raises(TextToSpeechServiceError):
            await _given_service(given_adapter).synthesize(text=_GIVEN_TEXT, locale=_GIVEN_LOCALE)
        # AND the adapter to have been called as many times as configured
        assert len(given_adapter.calls) == _NO_WAIT_RETRY.max_retries

    @pytest.mark.asyncio
    async def test_does_not_retry_a_permanent_failure(self):
        # GIVEN an adapter that fails with a permanent error
        given_adapter = _FakeAdapter(TextToSpeechAdapterError("invalid argument", status_code=400))

        # WHEN a text is synthesized
        # THEN expect a TextToSpeechServiceError
        with pytest.raises(TextToSpeechServiceError):
            await _given_service(given_adapter).synthesize(text=_GIVEN_TEXT, locale=_GIVEN_LOCALE)
        # AND the adapter to have been called once
        assert len(given_adapter.calls) == 1

    @pytest.mark.asyncio
    async def test_logs_the_sizes_and_the_locale_but_never_the_text(self, caplog):
        # GIVEN an adapter that fails once, then returns audio
        given_adapter = _FakeAdapter(TextToSpeechAdapterError("unavailable", status_code=503), _GIVEN_WAV)

        # WHEN a text is synthesized
        with caplog.at_level(logging.DEBUG):
            await _given_service(given_adapter).synthesize(text=_GIVEN_TEXT, locale=_GIVEN_LOCALE)

        # THEN expect the locale and the sizes to be logged
        assert _GIVEN_LOCALE.value in caplog.text
        assert f"wav_bytes={len(_GIVEN_WAV)}" in caplog.text
        # AND neither the text nor the style
        assert _GIVEN_TEXT not in caplog.text
        assert _GIVEN_VOICE.style not in caplog.text
