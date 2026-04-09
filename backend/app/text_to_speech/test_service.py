from unittest.mock import MagicMock, patch

import pytest

from app.text_to_speech.errors import EmptySynthesisError, TextToSpeechServiceError
from app.text_to_speech.service import GoogleTextToSpeechService


def _mock_synthesize_response(audio_content: bytes):
    """Create a mock SynthesizeSpeechResponse with the given audio content."""
    response = MagicMock()
    response.audio_content = audio_content
    return response


def _mock_empty_synthesize_response():
    """Create a mock SynthesizeSpeechResponse with no audio content."""
    response = MagicMock()
    response.audio_content = b""
    return response


@pytest.fixture()
def _set_env_vars(monkeypatch):
    """Set required environment variables for GoogleTextToSpeechService."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")


@pytest.mark.usefixtures("_set_env_vars")
class TestGoogleTextToSpeechService:
    """Tests for GoogleTextToSpeechService"""

    @pytest.mark.asyncio
    @patch("app.text_to_speech.service.texttospeech.TextToSpeechClient")
    async def test_synthesize_returns_audio_bytes_on_success(self, mock_tts_client_class):
        """Test that synthesize returns audio bytes on successful API call."""
        # GIVEN a service with a mocked TextToSpeechClient
        given_mock_client = MagicMock()
        mock_tts_client_class.return_value = given_mock_client
        # AND the client returns a response with audio content
        given_audio_content = b"fake-mp3-audio-data"
        given_response = _mock_synthesize_response(given_audio_content)
        given_mock_client.synthesize_speech.return_value = given_response
        # AND a valid text input
        given_text = "Hello world"
        given_language = "en-US"

        service = GoogleTextToSpeechService()

        # WHEN synthesize is called
        actual_result = await service.synthesize(text=given_text, language_code=given_language)

        # THEN expect the result to be the audio bytes
        assert actual_result == given_audio_content

    @pytest.mark.asyncio
    @patch("app.text_to_speech.service.texttospeech.TextToSpeechClient")
    async def test_synthesize_raises_empty_synthesis_error_when_no_audio(self, mock_tts_client_class):
        """Test that EmptySynthesisError is raised when TTS returns no audio content."""
        # GIVEN a service with a mocked TextToSpeechClient
        given_mock_client = MagicMock()
        mock_tts_client_class.return_value = given_mock_client
        # AND the client returns an empty response
        given_mock_client.synthesize_speech.return_value = _mock_empty_synthesize_response()
        given_text = "Hello world"

        service = GoogleTextToSpeechService()

        # WHEN synthesize is called
        # THEN expect EmptySynthesisError to be raised
        with pytest.raises(EmptySynthesisError):
            await service.synthesize(text=given_text, language_code="en-US")

    @pytest.mark.asyncio
    @patch("app.text_to_speech.service.texttospeech.TextToSpeechClient")
    async def test_synthesize_raises_service_error_on_api_failure(self, mock_tts_client_class):
        """Test that TextToSpeechServiceError is raised when the API call fails."""
        # GIVEN a service with a mocked TextToSpeechClient
        given_mock_client = MagicMock()
        mock_tts_client_class.return_value = given_mock_client
        # AND the client raises an exception
        given_mock_client.synthesize_speech.side_effect = Exception("API unavailable")
        given_text = "Hello world"

        service = GoogleTextToSpeechService()

        # WHEN synthesize is called
        # THEN expect TextToSpeechServiceError to be raised
        with pytest.raises(TextToSpeechServiceError):
            await service.synthesize(text=given_text, language_code="en-US")

    def test_constructor_raises_value_error_when_project_not_set(self, monkeypatch):
        """Test that initialization fails without GOOGLE_CLOUD_PROJECT."""
        # GIVEN GOOGLE_CLOUD_PROJECT is not set
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

        # WHEN the service is initialized
        # THEN expect a ValueError
        with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
            GoogleTextToSpeechService()

    @pytest.mark.asyncio
    @patch("app.text_to_speech.service.texttospeech.TextToSpeechClient")
    async def test_synthesize_uses_correct_voice_for_language(self, mock_tts_client_class):
        """Test that the correct Chirp 3 HD voice is selected for a known language."""
        # GIVEN a service with a mocked TextToSpeechClient
        given_mock_client = MagicMock()
        mock_tts_client_class.return_value = given_mock_client
        # AND the client returns a valid response
        given_response = _mock_synthesize_response(b"audio-data")
        given_mock_client.synthesize_speech.return_value = given_response
        # AND a Swahili language code
        given_language = "sw-KE"

        service = GoogleTextToSpeechService()

        # WHEN synthesize is called with the given language
        await service.synthesize(text="Habari", language_code=given_language)

        # THEN expect the client to have been called with the correct voice name
        actual_call_kwargs = given_mock_client.synthesize_speech.call_args
        actual_voice_params = actual_call_kwargs.kwargs.get("voice") or actual_call_kwargs[1].get("voice")
        assert actual_voice_params.name == "sw-KE-Chirp3-HD-Achernar"
        # AND the language code to match the voice prefix
        assert actual_voice_params.language_code == "sw-KE"

    @pytest.mark.asyncio
    @patch("app.text_to_speech.service.texttospeech.TextToSpeechClient")
    async def test_synthesize_falls_back_to_default_voice_for_unknown_language(self, mock_tts_client_class):
        """Test that an unknown language falls back to the default voice."""
        # GIVEN a service with a mocked TextToSpeechClient
        given_mock_client = MagicMock()
        mock_tts_client_class.return_value = given_mock_client
        # AND the client returns a valid response
        given_response = _mock_synthesize_response(b"audio-data")
        given_mock_client.synthesize_speech.return_value = given_response
        # AND an unknown language code
        given_language = "fr-FR"

        service = GoogleTextToSpeechService()

        # WHEN synthesize is called with the unknown language
        await service.synthesize(text="Bonjour", language_code=given_language)

        # THEN expect the client to have been called with the default voice name
        actual_call_kwargs = given_mock_client.synthesize_speech.call_args
        actual_voice_params = actual_call_kwargs.kwargs.get("voice") or actual_call_kwargs[1].get("voice")
        assert actual_voice_params.name == "en-US-Chirp3-HD-Achernar"
        # AND the language code to be the default voice prefix
        assert actual_voice_params.language_code == "en-US"
