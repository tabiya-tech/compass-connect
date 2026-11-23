from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors, types

from app.text_to_speech.adapter import GEMINI_TTS_LOCATION, GeminiTextToSpeechAdapter
from app.text_to_speech.errors import TextToSpeechAdapterError
from app.text_to_speech.types import VoiceSettings

_GIVEN_VOICE = VoiceSettings(language_code="en-US", voice="Kore", style="warm, clear and friendly")
_GIVEN_TEXT = "Tell me about your last job: what did you do there?"
_GIVEN_MODEL = "gemini-3.8-flash-tts"
_GIVEN_WAV = b"RIFF....WAVEfmt the audio"


def _given_response(*parts: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(candidates=[
        types.Candidate(content=types.Content(role="model", parts=list(parts)))
    ])


def _given_audio_part(audio: bytes) -> types.Part:
    return types.Part(inline_data=types.Blob(data=audio, mime_type="audio/wav"))


def _given_client(*, response: types.GenerateContentResponse | None = None,
                  error: Exception | None = None) -> MagicMock:
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        side_effect=error, return_value=response or _given_response(_given_audio_part(_GIVEN_WAV)))
    return client


def _given_api_error(code: int) -> errors.APIError:
    error_class = errors.ClientError if code < 500 else errors.ServerError
    return error_class(code, {"error": {"code": code, "message": "failed", "status": "FAILED"}})


class TestGeminiTextToSpeechAdapter:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_model", ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"])
    async def test_asks_the_configured_model_for_the_text_in_the_voice_style_and_language(self, given_model):
        # GIVEN a client that returns audio
        given_client = _given_client()
        given_adapter = GeminiTextToSpeechAdapter(model=given_model, client=given_client)

        # WHEN a text is synthesized
        await given_adapter.synthesize(text=_GIVEN_TEXT, voice=_GIVEN_VOICE)

        # THEN expect one request, to the configured model
        given_client.aio.models.generate_content.assert_awaited_once()
        actual_request = given_client.aio.models.generate_content.await_args.kwargs
        assert actual_request["model"] == given_model
        # AND the text, as it is, with the speaking style apart from it
        actual_contents: list[types.Content] = actual_request["contents"]
        assert len(actual_contents) == 1
        assert len(actual_contents[0].parts) == 1
        actual_part = actual_contents[0].parts[0]
        assert actual_part.text == _GIVEN_TEXT
        assert actual_part.speech_metadata.style == _GIVEN_VOICE.style
        # AND audio to be asked for, in the voice and the language
        actual_config: types.GenerateContentConfig = actual_request["config"]
        assert actual_config.response_modalities == [types.Modality.AUDIO]
        assert actual_config.speech_config.voice_config.voice == _GIVEN_VOICE.voice
        assert actual_config.speech_config.language_code == _GIVEN_VOICE.language_code

    @pytest.mark.asyncio
    async def test_sends_none_of_the_parameters_gemini_3_8_tts_rejects(self):
        # GIVEN the parameters Gemini 3.8 TTS rejects
        given_rejected_parameters = ["temperature", "top_p", "top_k", "candidate_count", "system_instruction"]
        # AND a client that returns audio
        given_client = _given_client()

        # WHEN a text is synthesized
        await GeminiTextToSpeechAdapter(model=_GIVEN_MODEL, client=given_client).synthesize(text=_GIVEN_TEXT,
                                                                                           voice=_GIVEN_VOICE)

        # THEN expect none of them in the request
        actual_config: types.GenerateContentConfig = (
            given_client.aio.models.generate_content.await_args.kwargs["config"])
        actual_sent = actual_config.model_dump(exclude_none=True)
        assert [parameter for parameter in given_rejected_parameters if parameter in actual_sent] == []

    @pytest.mark.asyncio
    async def test_returns_the_wav_audio_of_the_response(self):
        # GIVEN a response with a text part first, then the audio
        given_client = _given_client(response=_given_response(types.Part(text="some text"),
                                                               _given_audio_part(_GIVEN_WAV)))

        # WHEN a text is synthesized
        actual_audio = await GeminiTextToSpeechAdapter(model=_GIVEN_MODEL, client=given_client).synthesize(
            text=_GIVEN_TEXT, voice=_GIVEN_VOICE)

        # THEN expect the audio of the response
        assert actual_audio == _GIVEN_WAV

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_response", [
        types.GenerateContentResponse(candidates=[]),
        _given_response(types.Part(text="no audio")),
        _given_response(_given_audio_part(b"")),
    ], ids=["no candidate", "no audio part", "empty audio"])
    async def test_returns_no_audio_when_the_response_has_none(self, given_response):
        # GIVEN a response without audio
        given_client = _given_client(response=given_response)

        # WHEN a text is synthesized
        actual_audio = await GeminiTextToSpeechAdapter(model=_GIVEN_MODEL, client=given_client).synthesize(
            text=_GIVEN_TEXT, voice=_GIVEN_VOICE)

        # THEN expect no audio
        assert actual_audio == b""

    @pytest.mark.asyncio
    async def test_uses_the_shared_vertex_ai_client_of_the_location_of_gemini_tts(self):
        # GIVEN the shared Vertex AI client returns audio
        given_client = _given_client()

        # WHEN a text is synthesized by an adapter built without a client
        with patch("app.text_to_speech.adapter.get_genai_client", return_value=given_client) as mocked_get_client:
            await GeminiTextToSpeechAdapter(model=_GIVEN_MODEL).synthesize(text=_GIVEN_TEXT, voice=_GIVEN_VOICE)

        # THEN expect the client of the location of Gemini TTS
        mocked_get_client.assert_called_once_with(GEMINI_TTS_LOCATION)
        given_client.aio.models.generate_content.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_error", [
        _given_api_error(400),
        _given_api_error(403),
        _given_api_error(429),
        _given_api_error(500),
        _given_api_error(503),
    ], ids=["invalid argument", "permission denied", "rate limited", "internal error", "unavailable"])
    async def test_maps_api_errors_to_an_adapter_error_with_their_status(self, given_error):
        # GIVEN a client that fails
        given_adapter = GeminiTextToSpeechAdapter(model=_GIVEN_MODEL, client=_given_client(error=given_error))

        # WHEN a text is synthesized
        # THEN expect an adapter error with the HTTP status of the API error, so transient ones are retried
        with pytest.raises(TextToSpeechAdapterError) as actual_error:
            await given_adapter.synthesize(text=_GIVEN_TEXT, voice=_GIVEN_VOICE)
        assert actual_error.value.status_code == given_error.code
        # AND the error not to contain the text
        assert _GIVEN_TEXT not in str(actual_error.value)
