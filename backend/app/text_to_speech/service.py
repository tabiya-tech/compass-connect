import asyncio
import logging
import os
from abc import ABC, abstractmethod

from google.cloud import texttospeech

from app.text_to_speech.constants import DEFAULT_VOICE_NAME, LANGUAGE_TO_VOICE
from app.text_to_speech.errors import EmptySynthesisError, TextToSpeechServiceError
from common_libs.retry import Retry


class ITextToSpeechService(ABC):
    """Interface for text-to-speech synthesis services."""

    @abstractmethod
    async def synthesize(self, *, text: str, language_code: str) -> bytes:
        """
        Synthesize text into audio bytes.

        :param text: The text to synthesize into speech.
        :param language_code: The BCP-47 language code for synthesis (e.g. "en-US").
        :return: The synthesized audio bytes in MP3 format.
        :raises EmptySynthesisError: If no audio content is returned.
        :raises TextToSpeechServiceError: If the Google Cloud TTS API call fails.
        """
        raise NotImplementedError()


class GoogleTextToSpeechService(ITextToSpeechService):
    """Google Cloud Text-to-Speech implementation."""

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)

        # Validate that the GCP project is configured (required for authentication context)
        if not os.getenv("GOOGLE_CLOUD_PROJECT"):
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set")

        self._client = texttospeech.TextToSpeechClient()

    async def synthesize(self, *, text: str, language_code: str) -> bytes:
        # Look up the voice name for the given language, falling back to default
        voice_name = LANGUAGE_TO_VOICE.get(language_code, DEFAULT_VOICE_NAME)

        # Extract the language code prefix from the voice name (e.g. "en-US" from "en-US-Chirp3-HD-Achernar")
        voice_language_code = "-".join(voice_name.split("-")[:2])

        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice_params = texttospeech.VoiceSelectionParams(
            language_code=voice_language_code,
            name=voice_name,
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
        )

        try:
            response = await Retry[texttospeech.SynthesizeSpeechResponse].call_with_exponential_backoff(
                callback=lambda: asyncio.to_thread(
                    self._client.synthesize_speech,
                    input=synthesis_input,
                    voice=voice_params,
                    audio_config=audio_config,
                ),
                logger=self._logger,
            )
        except Exception as e:
            self._logger.error("Text-to-speech API call failed", exc_info=True)
            raise TextToSpeechServiceError(detail=str(e)) from e

        if not response.audio_content:
            raise EmptySynthesisError()

        return response.audio_content
