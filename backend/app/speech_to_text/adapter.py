import asyncio
from abc import ABC, abstractmethod
from typing import Optional

from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import GoogleAPIError
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech

from app.speech_to_text.errors import SpeechToTextAdapterError
from app.speech_to_text.types import AudioUpload, SpeechToTextModel

CHIRP_LOCATION = "us"
""" The multi-region Chirp 3 runs in, so where the audio is processed (Chirp 3 runs in "us" and "eu" only). """


class ISpeechToTextAdapter(ABC):
    """
    Sends one recognition request to the external speech-to-text service.
    """

    @abstractmethod
    async def recognize(self, *, audio: AudioUpload, language_code: str) -> str:
        """
        :param audio: the recording
        :param language_code: the language spoken in it, as a BCP-47 code, e.g. "sw-KE"
        :return: the raw transcript, possibly empty
        :raises SpeechToTextAdapterError: if the external service fails
        """
        raise NotImplementedError()


class ChirpSpeechToTextAdapter(ISpeechToTextAdapter):
    """
    Transcribes recordings with Chirp 3, through the synchronous Recognize method of Speech-to-Text v2.
    """

    def __init__(self, *, project_id: str, model: SpeechToTextModel, client: Optional[SpeechClient] = None):
        """
        :param project_id: the Google Cloud project that is billed
        :param model: the Speech-to-Text model
        :param client: the Google client, by default one for the regional endpoint of CHIRP_LOCATION
        """
        self._recognizer = f"projects/{project_id}/locations/{CHIRP_LOCATION}/recognizers/_"
        self._model = model
        self._client = client or SpeechClient(
            client_options=ClientOptions(api_endpoint=f"{CHIRP_LOCATION}-speech.googleapis.com"))

    async def recognize(self, *, audio: AudioUpload, language_code: str) -> str:
        request = cloud_speech.RecognizeRequest(
            recognizer=self._recognizer,
            config=cloud_speech.RecognitionConfig(
                auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                language_codes=[language_code],
                model=self._model,
                features=cloud_speech.RecognitionFeatures(enable_automatic_punctuation=True),
            ),
            content=audio.content,
        )
        try:
            response = await asyncio.to_thread(self._client.recognize, request=request)
        except GoogleAPIError as e:
            status_code = getattr(e, "code", None)
            raise SpeechToTextAdapterError(
                f"Chirp recognition request failed: {type(e).__name__}",
                status_code=status_code if isinstance(status_code, int) else None) from e
        # Each result is a consecutive part of the audio; its first alternative is the most likely one.
        return " ".join(result.alternatives[0].transcript.strip()
                        for result in response.results if result.alternatives).strip()
