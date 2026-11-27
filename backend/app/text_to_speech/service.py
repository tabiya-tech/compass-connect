import asyncio
import logging
from abc import ABC, abstractmethod

from app.i18n.types import Locale
from app.text_to_speech.adapter import ITextToSpeechAdapter
from app.text_to_speech.audio import AudioConversionError, wav_to_mp3
from app.text_to_speech.errors import (EmptySynthesisError, LocaleNotEnabledError, TextToSpeechAdapterError,
                                       TextToSpeechServiceError)
from app.text_to_speech.types import SynthesisText, SynthesizedAudio, TextToSpeechConfig, VoiceSettings
from common_libs.retry import Retry, RetryConfigWithExponentialBackOff, RetryLimitExceededError

logger = logging.getLogger(__name__)

DEFAULT_RETRY_CONFIG = RetryConfigWithExponentialBackOff(max_retries=3, initial_wait=0.5)
""" The user waits for the audio, so a few quick attempts only. """


class ITextToSpeechService(ABC):
    """
    Reads texts aloud in the voice of their locale.
    """

    @abstractmethod
    async def synthesize(self, *, text: SynthesisText, locale: Locale) -> SynthesizedAudio:
        """
        :param text: the plain text to read aloud
        :param locale: the locale of the text
        :return: the audio of the text
        :raises LocaleNotEnabledError: if read aloud is not offered in the locale
        :raises EmptySynthesisError: if the external service returned no audio
        :raises TextToSpeechServiceError: if the external service failed
        """
        raise NotImplementedError()


class TextToSpeechService(ITextToSpeechService):
    def __init__(self, *, config: TextToSpeechConfig, adapter: ITextToSpeechAdapter,
                 retry_config: RetryConfigWithExponentialBackOff = DEFAULT_RETRY_CONFIG):
        self._config = config
        self._adapter = adapter
        self._retry_config = retry_config

    async def synthesize(self, *, text: SynthesisText, locale: Locale) -> SynthesizedAudio:
        locale_settings = self._config.locale_settings(locale)
        if locale_settings is None:
            raise LocaleNotEnabledError(locale)
        voice = VoiceSettings(language_code=self._config.language_code(locale), voice=locale_settings.voice,
                              style=locale_settings.style)

        async def _synthesize() -> bytes:
            return await self._adapter.synthesize(text=text, voice=voice)

        try:
            wav = await Retry[bytes].call_with_exponential_backoff(callback=_synthesize,
                                                                     retry_config=self._retry_config,
                                                                     logger=logger)
        except (TextToSpeechAdapterError, RetryLimitExceededError) as e:
            raise TextToSpeechServiceError(f"Text-to-speech failed for the locale {locale.value}") from e

        if not wav:
            raise EmptySynthesisError(f"Text-to-speech returned no audio for the locale {locale.value}")

        # Gemini TTS returns WAV, the route and the frontend take MP3. The encoding takes CPU time, so it runs in a worker
        # thread, not on the event loop
        try:
            audio = await asyncio.to_thread(wav_to_mp3, wav)
        except AudioConversionError as e:
            raise TextToSpeechServiceError(f"Text-to-speech returned audio that cannot be read, for the locale "
                                           f"{locale.value}") from e

        logger.info("Synthesized speech {locale='%s', text_bytes=%s, wav_bytes=%s, audio_bytes=%s}", locale.value,
                    len(text.encode("utf-8")), len(wav), len(audio))
        return SynthesizedAudio(content=audio, media_type="audio/mpeg", locale=locale)
