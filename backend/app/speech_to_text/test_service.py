from unittest.mock import MagicMock, patch

import pytest

from app.speech_to_text.errors import EmptyTranscriptionError, SpeechToTextServiceError
from app.speech_to_text.service import GoogleSpeechToTextService


def _mock_recognize_response(transcripts: list[str]):
    """Create a mock RecognizeResponse with the given transcript texts."""
    response = MagicMock()
    results = []
    for text in transcripts:
        alternative = MagicMock()
        alternative.transcript = text
        result = MagicMock()
        result.alternatives = [alternative]
        results.append(result)
    response.results = results
    return response


def _mock_empty_recognize_response():
    """Create a mock RecognizeResponse with no results."""
    response = MagicMock()
    response.results = []
    return response


@pytest.fixture()
def _set_env_vars(monkeypatch):
    """Set required environment variables for GoogleSpeechToTextService."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("VERTEX_API_REGION", "us-central1")


@pytest.mark.usefixtures("_set_env_vars")
class TestGoogleSpeechToTextService:
    """Tests for GoogleSpeechToTextService"""

    @pytest.mark.asyncio
    @patch("app.speech_to_text.service.SpeechClient")
    async def test_transcribe_returns_concatenated_text_on_success(self, mock_speech_client_class):
        """Test that transcription results are concatenated correctly."""
        # GIVEN a service with a mocked SpeechClient
        given_mock_client = MagicMock()
        mock_speech_client_class.return_value = given_mock_client
        # AND the client returns a response with multiple transcript parts
        given_response = _mock_recognize_response(["hello", "world"])
        given_mock_client.recognize.return_value = given_response
        # AND a valid audio input
        given_audio_bytes = b"fake-audio"
        given_language = "en-US"

        service = GoogleSpeechToTextService()

        # WHEN transcribe is called
        actual_result = await service.transcribe(audio_bytes=given_audio_bytes, language_code=given_language)

        # THEN expect the text to be the concatenated transcripts
        assert actual_result.text == "hello world"
        # AND the language code to match the given language
        assert actual_result.language_code == given_language

    @pytest.mark.asyncio
    @patch("app.speech_to_text.service.SpeechClient")
    async def test_transcribe_raises_empty_transcription_error_when_no_results(self, mock_speech_client_class):
        """Test that EmptyTranscriptionError is raised when STT returns no results."""
        # GIVEN a service with a mocked SpeechClient
        given_mock_client = MagicMock()
        mock_speech_client_class.return_value = given_mock_client
        # AND the client returns an empty response
        given_mock_client.recognize.return_value = _mock_empty_recognize_response()
        given_audio_bytes = b"fake-audio"

        service = GoogleSpeechToTextService()

        # WHEN transcribe is called
        # THEN expect EmptyTranscriptionError to be raised
        with pytest.raises(EmptyTranscriptionError):
            await service.transcribe(audio_bytes=given_audio_bytes, language_code="en-US")

    @pytest.mark.asyncio
    @patch("app.speech_to_text.service.SpeechClient")
    async def test_transcribe_raises_service_error_when_api_fails(self, mock_speech_client_class):
        """Test that SpeechToTextServiceError is raised when the API call fails."""
        # GIVEN a service with a mocked SpeechClient
        given_mock_client = MagicMock()
        mock_speech_client_class.return_value = given_mock_client
        # AND the client raises an exception
        given_mock_client.recognize.side_effect = Exception("API unavailable")
        given_audio_bytes = b"fake-audio"

        service = GoogleSpeechToTextService()

        # WHEN transcribe is called
        # THEN expect SpeechToTextServiceError to be raised
        with pytest.raises(SpeechToTextServiceError):
            await service.transcribe(audio_bytes=given_audio_bytes, language_code="en-US")

    def test_init_raises_when_google_cloud_project_not_set(self, monkeypatch):
        """Test that initialization fails without GOOGLE_CLOUD_PROJECT."""
        # GIVEN GOOGLE_CLOUD_PROJECT is not set
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

        # WHEN the service is initialized
        # THEN expect a ValueError
        with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
            GoogleSpeechToTextService()
