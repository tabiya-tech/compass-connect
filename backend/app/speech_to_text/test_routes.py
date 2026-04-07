import io
from http import HTTPStatus
from unittest.mock import AsyncMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.speech_to_text.errors import EmptyTranscriptionError, SpeechToTextServiceError
from app.speech_to_text.routes import add_speech_to_text_routes, get_speech_to_text_service
from app.speech_to_text.service import ISpeechToTextService
from app.speech_to_text.types import TranscriptionResponse
from common_libs.test_utilities.mock_auth import MockAuth, UnauthenticatedMockAuth


class _MockSpeechToTextService(ISpeechToTextService):
    """Mock implementation for testing."""

    def __init__(self):
        self.transcribe_mock = AsyncMock()

    async def transcribe(self, *, audio_bytes: bytes, language_code: str) -> TranscriptionResponse:
        return await self.transcribe_mock(audio_bytes=audio_bytes, language_code=language_code)


def _given_audio_file(content: bytes = b"fake-audio-data", content_type: str = "audio/webm"):
    """Create a mock audio file for upload."""
    return ("audio", ("recording.webm", io.BytesIO(content), content_type))


def _create_test_client(auth=None):
    """Set up a test client with mocked dependencies."""
    if auth is None:
        auth = MockAuth()
    mock_service = _MockSpeechToTextService()
    app = FastAPI()
    app.dependency_overrides[get_speech_to_text_service] = lambda: mock_service
    add_speech_to_text_routes(app, authentication=auth)
    client = TestClient(app)
    return client, mock_service, auth


class TestTranscribeAudioEndpoint:
    """Tests for POST /speech-to-text/transcribe"""

    def test_respond_with_status_ok_and_transcription_on_success(self):
        """Test successful transcription with default language."""
        # GIVEN a valid audio file
        given_audio = _given_audio_file()
        # AND a service that returns a successful transcription
        client, mock_service, _auth = _create_test_client()
        given_response = TranscriptionResponse(text="hello world", language_code="en-US")
        mock_service.transcribe_mock.return_value = given_response

        # WHEN the transcribe endpoint is called
        actual_response = client.post("/speech-to-text/transcribe", files=[given_audio], data={"language": "en-US"})

        # THEN expect the response status to be OK
        assert actual_response.status_code == HTTPStatus.OK
        # AND the response body to contain the transcribed text
        actual_body = actual_response.json()
        assert actual_body["text"] == "hello world"
        assert actual_body["language_code"] == "en-US"

    def test_respond_with_status_ok_when_explicit_language_provided(self):
        """Test successful transcription with an explicit language."""
        # GIVEN a valid audio file
        given_audio = _given_audio_file()
        # AND an explicit language
        given_language = "sw-KE"
        # AND a service that returns a successful transcription
        client, mock_service, _auth = _create_test_client()
        given_response = TranscriptionResponse(text="habari", language_code=given_language)
        mock_service.transcribe_mock.return_value = given_response

        # WHEN the transcribe endpoint is called with the given language
        actual_response = client.post(
            "/speech-to-text/transcribe",
            files=[given_audio],
            data={"language": given_language},
        )

        # THEN expect the response status to be OK
        assert actual_response.status_code == HTTPStatus.OK
        # AND the language code to match the given language
        assert actual_response.json()["language_code"] == given_language

    def test_respond_with_status_unsupported_media_type_for_invalid_mime(self):
        """Test that unsupported audio formats are rejected."""
        # GIVEN an audio file with an unsupported MIME type
        given_audio = _given_audio_file(content_type="application/pdf")
        client, _mock_service, _auth = _create_test_client()

        # WHEN the transcribe endpoint is called
        actual_response = client.post("/speech-to-text/transcribe", files=[given_audio], data={"language": "en-US"})

        # THEN expect the response status to be UNSUPPORTED_MEDIA_TYPE
        assert actual_response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    def test_respond_with_status_ok_when_mime_type_has_space_after_semicolon(self):
        """Test that MIME types with spaces after semicolons are accepted."""
        # GIVEN an audio file with a space after the semicolon in the MIME type
        given_audio = _given_audio_file(content_type="audio/webm; codecs=opus")
        # AND a service that returns a successful transcription
        client, mock_service, _auth = _create_test_client()
        given_response = TranscriptionResponse(text="hello", language_code="en-US")
        mock_service.transcribe_mock.return_value = given_response

        # WHEN the transcribe endpoint is called
        actual_response = client.post("/speech-to-text/transcribe", files=[given_audio], data={"language": "en-US"})

        # THEN expect the response status to be OK
        assert actual_response.status_code == HTTPStatus.OK

    def test_respond_with_status_entity_too_large_for_oversized_audio(self):
        """Test that oversized audio files are rejected."""
        # GIVEN an audio file that exceeds the maximum size
        given_large_content = b"x" * (10 * 1024 * 1024 + 1)
        given_audio = _given_audio_file(content=given_large_content)
        client, _mock_service, _auth = _create_test_client()

        # WHEN the transcribe endpoint is called
        actual_response = client.post("/speech-to-text/transcribe", files=[given_audio], data={"language": "en-US"})

        # THEN expect the response status to be REQUEST_ENTITY_TOO_LARGE
        assert actual_response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    def test_respond_with_status_unprocessable_entity_when_transcription_is_empty(self):
        """Test that empty transcription results return 422."""
        # GIVEN a valid audio file
        given_audio = _given_audio_file()
        # AND a service that raises EmptyTranscriptionError
        client, mock_service, _auth = _create_test_client()
        mock_service.transcribe_mock.side_effect = EmptyTranscriptionError()

        # WHEN the transcribe endpoint is called
        actual_response = client.post("/speech-to-text/transcribe", files=[given_audio], data={"language": "en-US"})

        # THEN expect the response status to be UNPROCESSABLE_ENTITY
        assert actual_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_respond_with_status_bad_gateway_when_service_fails(self):
        """Test that Google STT API failures return 502."""
        # GIVEN a valid audio file
        given_audio = _given_audio_file()
        # AND a service that raises SpeechToTextServiceError
        client, mock_service, _auth = _create_test_client()
        mock_service.transcribe_mock.side_effect = SpeechToTextServiceError(detail="API unavailable")

        # WHEN the transcribe endpoint is called
        actual_response = client.post("/speech-to-text/transcribe", files=[given_audio], data={"language": "en-US"})

        # THEN expect the response status to be BAD_GATEWAY
        assert actual_response.status_code == HTTPStatus.BAD_GATEWAY

    def test_respond_with_status_internal_server_error_on_unexpected_error(self):
        """Test that unexpected errors return 500."""
        # GIVEN a valid audio file
        given_audio = _given_audio_file()
        # AND a service that raises an unexpected error
        client, mock_service, _auth = _create_test_client()
        mock_service.transcribe_mock.side_effect = RuntimeError("something broke")

        # WHEN the transcribe endpoint is called
        actual_response = client.post("/speech-to-text/transcribe", files=[given_audio], data={"language": "en-US"})

        # THEN expect the response status to be INTERNAL_SERVER_ERROR
        assert actual_response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_respond_with_status_unauthorized_when_not_authenticated(self):
        """Test that unauthenticated requests are rejected."""
        # GIVEN an unauthenticated user
        given_audio = _given_audio_file()
        client, _mock_service, _auth = _create_test_client(auth=UnauthenticatedMockAuth())

        # WHEN the transcribe endpoint is called
        actual_response = client.post("/speech-to-text/transcribe", files=[given_audio], data={"language": "en-US"})

        # THEN expect the response status to be UNAUTHORIZED
        assert actual_response.status_code == HTTPStatus.UNAUTHORIZED

    def test_respond_with_status_bad_request_for_empty_audio(self):
        """Test that empty audio files are rejected."""
        # GIVEN an empty audio file
        given_audio = _given_audio_file(content=b"")
        client, _mock_service, _auth = _create_test_client()

        # WHEN the transcribe endpoint is called
        actual_response = client.post("/speech-to-text/transcribe", files=[given_audio], data={"language": "en-US"})

        # THEN expect the response status to be BAD_REQUEST
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
