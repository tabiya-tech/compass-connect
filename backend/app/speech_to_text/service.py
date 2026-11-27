import logging
from abc import ABC, abstractmethod

from app.i18n.types import Locale
from app.speech_to_text.adapter import ISpeechToTextAdapter
from app.speech_to_text.errors import (EmptyTranscriptionError, LocaleNotEnabledError, SpeechToTextAdapterError,
                                       SpeechToTextServiceError)
from app.speech_to_text.types import AudioUpload, SpeechToTextConfig, Transcription
from common_libs.retry import Retry, RetryConfigWithExponentialBackOff, RetryLimitExceededError

logger = logging.getLogger(__name__)

DEFAULT_RETRY_CONFIG = RetryConfigWithExponentialBackOff(max_retries=3, initial_wait=0.5)
""" The user waits for the transcript, so a few quick attempts only. """


class ISpeechToTextService(ABC):
    """
    Transcribes recordings in the language of their locale.
    """

    @abstractmethod
    async def transcribe(self, *, audio: AudioUpload, locale: Locale) -> Transcription:
        """
        :param audio: the recording
        :param locale: the locale the user speaks in
        :return: the transcript
        :raises LocaleNotEnabledError: if voice input is not offered in the locale
        :raises EmptyTranscriptionError: if no speech was recognized
        :raises SpeechToTextServiceError: if the external service failed
        """
        raise NotImplementedError()


class SpeechToTextService(ISpeechToTextService):
    def __init__(self, *, config: SpeechToTextConfig, adapter: ISpeechToTextAdapter,
                 retry_config: RetryConfigWithExponentialBackOff = DEFAULT_RETRY_CONFIG):
        self._config = config
        self._adapter = adapter
        self._retry_config = retry_config

    async def transcribe(self, *, audio: AudioUpload, locale: Locale) -> Transcription:
        if not self._config.is_locale_enabled(locale):
            raise LocaleNotEnabledError(locale)
        language_code = self._config.language_code(locale)

        async def _recognize() -> str:
            return await self._adapter.recognize(audio=audio, language_code=language_code)

        try:
            transcript = await Retry[str].call_with_exponential_backoff(callback=_recognize,
                                                                       retry_config=self._retry_config,
                                                                       logger=logger)
        except (SpeechToTextAdapterError, RetryLimitExceededError) as e:
            raise SpeechToTextServiceError(f"Speech-to-text failed for the locale {locale.value}") from e

        text = transcript.strip()
        if not text:
            raise EmptyTranscriptionError(f"No speech was recognized for the locale {locale.value}")

        logger.info("Transcribed audio {locale='%s', audio_bytes=%s, mime_type='%s', transcript_length=%s}",
                    locale.value, len(audio.content), audio.mime_type, len(text))
        return Transcription(text=text, locale=locale)
