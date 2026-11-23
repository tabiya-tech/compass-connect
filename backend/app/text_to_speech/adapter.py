from abc import ABC, abstractmethod
from typing import Optional

from google import genai
from google.genai import errors, types

from app.text_to_speech.errors import TextToSpeechAdapterError
from app.text_to_speech.types import SynthesisText, TextToSpeechModel, VoiceSettings
from common_libs.llm.generative_models import get_genai_client

GEMINI_TTS_LOCATION = "global"
""" Where Gemini 3.8 TTS runs on Vertex AI (also "us" and "eu"). """


class ITextToSpeechAdapter(ABC):
    """
    Sends one synthesis request to the external text-to-speech service.
    """

    @abstractmethod
    async def synthesize(self, *, text: SynthesisText, voice: VoiceSettings) -> bytes:
        """
        :param text: the plain text to read aloud
        :param voice: how to speak it
        :return: the audio as a WAV file, possibly empty
        :raises TextToSpeechAdapterError: if the external service fails
        """
        raise NotImplementedError()


class GeminiTextToSpeechAdapter(ITextToSpeechAdapter):
    """
    Reads texts aloud with Gemini 3.8 TTS, through the generateContent method of Vertex AI.
    The models return a WAV file (16-bit PCM, 24 kHz, mono). They reject the sampling parameters (temperature, top_p,
    top_k, candidate_count) and system instructions, so none is sent.
    """

    def __init__(self, *, model: TextToSpeechModel, client: Optional[genai.Client] = None):
        """
        :param model: the Gemini 3.8 TTS model
        :param client: the google-genai client, by default the shared Vertex AI client of GEMINI_TTS_LOCATION
        """
        self._model = model
        self._client = client

    async def synthesize(self, *, text: SynthesisText, voice: VoiceSettings) -> bytes:
        client = self._client or get_genai_client(GEMINI_TTS_LOCATION)
        try:
            response = await client.aio.models.generate_content(
                model=self._model,
                # the text is sent as it is, the speaking style apart from it, so it is not read aloud
                contents=[types.Content(role="user", parts=[
                    types.Part(text=text, speech_metadata=types.SpeechMetadata(style=voice.style)),
                ])],
                config=types.GenerateContentConfig(
                    response_modalities=[types.Modality.AUDIO],
                    speech_config=types.SpeechConfig(
                        language_code=voice.language_code,
                        voice_config=types.VoiceConfig(voice=voice.voice),
                    ),
                ),
            )
        except errors.APIError as e:
            raise TextToSpeechAdapterError(f"Gemini TTS request failed: {type(e).__name__} {e.code}",
                                           status_code=e.code) from e
        # the audio is the inline data of the first part that has some; google-genai decodes its base64
        for part in response.parts or []:
            if part.inline_data and part.inline_data.data:
                return part.inline_data.data
        return b""
