import logging

import pytest

from app.i18n.types import Locale
from app.speech_to_text.adapter import ISpeechToTextAdapter
from app.speech_to_text.errors import (EmptyTranscriptionError, LocaleNotEnabledError, SpeechToTextAdapterError,
                                       SpeechToTextServiceError)
from app.speech_to_text.service import SpeechToTextService
from app.speech_to_text.types import AudioUpload, SpeechToTextConfig
from common_libs.retry import RetryConfigWithExponentialBackOff

_GIVEN_AUDIO = AudioUpload(content=b"webm-opus-recording", mime_type="audio/webm")
_GIVEN_TRANSCRIPT = "I worked as a carpenter for three years."
_NO_WAIT_RETRY = RetryConfigWithExponentialBackOff(max_retries=3, initial_wait=0, base_backoff_factor=1, jitter=0)


class _FakeAdapter(ISpeechToTextAdapter):
    """ Answers with the given outcomes in order: a transcript, or an exception to raise. """

    def __init__(self, *outcomes: str | Exception):
        self._outcomes = list(outcomes)
        self.calls: list[tuple[AudioUpload, str]] = []

    async def recognize(self, *, audio, language_code):
        self.calls.append((audio, language_code))
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


_GIVEN_LOCALE = Locale.EN_GB
_GIVEN_UNCONFIGURED_LOCALE = Locale.ES_ES


def _given_service(adapter: ISpeechToTextAdapter, *, enabled: bool = True) -> SpeechToTextService:
    config = SpeechToTextConfig.model_validate({"enabled": enabled, "locales": [_GIVEN_LOCALE.value]})
    return SpeechToTextService(config=config, adapter=adapter, retry_config=_NO_WAIT_RETRY)


class TestSpeechToTextService:
    @pytest.mark.asyncio
    async def test_transcribes_in_the_language_configured_for_the_locale(self):
        # GIVEN an adapter that recognizes speech
        given_adapter = _FakeAdapter(_GIVEN_TRANSCRIPT)

        # WHEN a recording in a locale mapped to another language code is transcribed
        actual_transcription = await _given_service(given_adapter).transcribe(audio=_GIVEN_AUDIO, locale=_GIVEN_LOCALE)

        # THEN expect the transcript, in the locale
        assert actual_transcription.text == _GIVEN_TRANSCRIPT
        assert actual_transcription.locale == _GIVEN_LOCALE
        # AND the adapter to have been asked once, for the configured language code
        assert given_adapter.calls == [(_GIVEN_AUDIO, _GIVEN_LOCALE.value)]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_locale, given_enabled", [
        (_GIVEN_UNCONFIGURED_LOCALE, True),
        (_GIVEN_LOCALE, False),
    ], ids=["locale not configured", "feature off"])
    async def test_rejects_a_locale_without_voice_input_without_calling_the_adapter(self, given_locale, given_enabled):
        # GIVEN an adapter
        given_adapter = _FakeAdapter(_GIVEN_TRANSCRIPT)

        # WHEN a recording in a locale without voice input is transcribed
        # THEN expect a LocaleNotEnabledError
        with pytest.raises(LocaleNotEnabledError):
            await _given_service(given_adapter, enabled=given_enabled).transcribe(audio=_GIVEN_AUDIO,
                                                                                 locale=given_locale)
        # AND the adapter not to have been called, so no other language is used
        assert given_adapter.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_transcript", ["", "  \n "], ids=["empty", "whitespace only"])
    async def test_raises_an_empty_transcription_error_when_no_speech_is_recognized(self, given_transcript):
        # GIVEN an adapter that recognizes no speech
        given_adapter = _FakeAdapter(given_transcript)

        # WHEN a recording is transcribed
        # THEN expect an EmptyTranscriptionError
        with pytest.raises(EmptyTranscriptionError):
            await _given_service(given_adapter).transcribe(audio=_GIVEN_AUDIO, locale=_GIVEN_LOCALE)

    @pytest.mark.asyncio
    async def test_trims_the_transcript(self):
        # GIVEN an adapter whose transcript has surrounding whitespace
        given_adapter = _FakeAdapter(f"  {_GIVEN_TRANSCRIPT}\n")

        # WHEN a recording is transcribed
        actual_transcription = await _given_service(given_adapter).transcribe(audio=_GIVEN_AUDIO, locale=_GIVEN_LOCALE)

        # THEN expect the trimmed transcript
        assert actual_transcription.text == _GIVEN_TRANSCRIPT

    @pytest.mark.asyncio
    async def test_retries_a_transient_failure(self):
        # GIVEN an adapter that fails once with a transient error, then recognizes speech
        given_adapter = _FakeAdapter(SpeechToTextAdapterError("unavailable", status_code=503), _GIVEN_TRANSCRIPT)

        # WHEN a recording is transcribed
        actual_transcription = await _given_service(given_adapter).transcribe(audio=_GIVEN_AUDIO, locale=_GIVEN_LOCALE)

        # THEN expect the transcript
        assert actual_transcription.text == _GIVEN_TRANSCRIPT
        # AND the adapter to have been called twice
        assert len(given_adapter.calls) == 2

    @pytest.mark.asyncio
    async def test_gives_up_after_the_configured_attempts(self):
        # GIVEN an adapter that keeps failing with a transient error
        given_adapter = _FakeAdapter(SpeechToTextAdapterError("deadline exceeded", status_code=504))

        # WHEN a recording is transcribed
        # THEN expect a SpeechToTextServiceError
        with pytest.raises(SpeechToTextServiceError):
            await _given_service(given_adapter).transcribe(audio=_GIVEN_AUDIO, locale=_GIVEN_LOCALE)
        # AND the adapter to have been called as many times as configured
        assert len(given_adapter.calls) == _NO_WAIT_RETRY.max_retries

    @pytest.mark.asyncio
    async def test_does_not_retry_a_permanent_failure(self):
        # GIVEN an adapter that fails with a permanent error
        given_adapter = _FakeAdapter(SpeechToTextAdapterError("permission denied", status_code=403))

        # WHEN a recording is transcribed
        # THEN expect a SpeechToTextServiceError
        with pytest.raises(SpeechToTextServiceError):
            await _given_service(given_adapter).transcribe(audio=_GIVEN_AUDIO, locale=_GIVEN_LOCALE)
        # AND the adapter to have been called once
        assert len(given_adapter.calls) == 1

    @pytest.mark.asyncio
    async def test_logs_the_sizes_and_the_locale_but_never_the_audio_or_the_transcript(self, caplog):
        # GIVEN an adapter that fails once, then recognizes speech
        given_adapter = _FakeAdapter(SpeechToTextAdapterError("unavailable", status_code=503), _GIVEN_TRANSCRIPT)

        # WHEN a recording is transcribed
        with caplog.at_level(logging.DEBUG):
            await _given_service(given_adapter).transcribe(audio=_GIVEN_AUDIO, locale=_GIVEN_LOCALE)

        # THEN expect the locale and the size of the recording to be logged
        assert _GIVEN_LOCALE.value in caplog.text
        assert f"audio_bytes={len(_GIVEN_AUDIO.content)}" in caplog.text
        # AND neither the audio nor the transcript
        assert _GIVEN_AUDIO.content.decode() not in caplog.text
        assert _GIVEN_TRANSCRIPT not in caplog.text
