import asyncio
import logging
import os
from abc import ABC, abstractmethod

from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech

from app.speech_to_text.errors import EmptyTranscriptionError, SpeechToTextServiceError
from app.speech_to_text.types import TranscriptionResponse
from common_libs.retry import Retry


class ISpeechToTextService(ABC):
    """Interface for speech-to-text transcription services."""

    @abstractmethod
    async def transcribe(self, *, audio_bytes: bytes, language_code: str) -> TranscriptionResponse:
        """
        Transcribe audio bytes to text.

        :param audio_bytes: The raw audio bytes to transcribe.
        :param language_code: The BCP-47 language code for transcription (e.g. "en-US").
        :return: The transcription response containing the text and language code.
        :raises EmptyTranscriptionError: If no transcription results are returned.
        :raises SpeechToTextServiceError: If the Google Cloud STT API call fails.
        """
        raise NotImplementedError()


class GoogleSpeechToTextService(ISpeechToTextService):
    """Google Cloud Speech-to-Text v2 implementation."""

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)

        self._project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not self._project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set")

        self._region = os.getenv("VERTEX_API_REGION", "us-central1")

        # Create the client with regional endpoint
        self._client = SpeechClient(
            client_options={"api_endpoint": f"{self._region}-speech.googleapis.com"}
        )

    async def transcribe(self, *, audio_bytes: bytes, language_code: str) -> TranscriptionResponse:
        recognizer = f"projects/{self._project_id}/locations/{self._region}/recognizers/_"

        config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=[language_code],
            model="long",
        )

        request = cloud_speech.RecognizeRequest(
            recognizer=recognizer,
            config=config,
            content=audio_bytes,
        )

        try:
            response = await Retry[cloud_speech.RecognizeResponse].call_with_exponential_backoff(
                callback=lambda: asyncio.to_thread(self._client.recognize, request=request),
                logger=self._logger,
            )
        except Exception as e:
            self._logger.error("Speech-to-text API call failed", exc_info=True)
            raise SpeechToTextServiceError(detail=str(e)) from e

        # Concatenate all transcript alternatives
        transcript_parts = []
        for result in response.results:
            if result.alternatives:
                transcript_parts.append(result.alternatives[0].transcript)

        text = " ".join(transcript_parts).strip()

        if not text:
            raise EmptyTranscriptionError()

        return TranscriptionResponse(
            text=text,
            language_code=language_code,
        )
