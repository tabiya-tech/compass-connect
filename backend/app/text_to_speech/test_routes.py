from http import HTTPStatus
from unittest.mock import AsyncMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.text_to_speech.constants import MAX_TEXT_LENGTH
from app.text_to_speech.errors import EmptySynthesisError, TextToSpeechServiceError
from app.text_to_speech.routes import add_text_to_speech_routes, get_text_to_speech_service
from app.text_to_speech.service import ITextToSpeechService
from common_libs.test_utilities.mock_auth import MockAuth, UnauthenticatedMockAuth


class _MockTextToSpeechService(ITextToSpeechService):
    """Mock implementation for testing."""

    def __init__(self):
        self.synthesize_mock = AsyncMock()

    async def synthesize(self, *, text: str, language_code: str) -> bytes:
        return await self.synthesize_mock(text=text, language_code=language_code)


def _create_test_client(auth=None):
    """Set up a test client with mocked dependencies."""
    if auth is None:
        auth = MockAuth()
    mock_service = _MockTextToSpeechService()
    app = FastAPI()
    app.dependency_overrides[get_text_to_speech_service] = lambda: mock_service
    add_text_to_speech_routes(app, authentication=auth)
    client = TestClient(app)
    return client, mock_service, auth


class TestSynthesizeSpeechEndpoint:
    """Tests for POST /text-to-speech/synthesize"""

    def test_respond_with_status_ok_and_audio_on_success(self):
        """Test successful synthesis returns audio bytes."""
        # GIVEN a valid text input
        given_text = "Hello world"
        # AND a service that returns audio bytes
        client, mock_service, _auth = _create_test_client()
        given_audio_bytes = b"fake-audio-content"
        mock_service.synthesize_mock.return_value = given_audio_bytes

        # WHEN the synthesize endpoint is called
        actual_response = client.post(
            "/text-to-speech/synthesize",
            json={"text": given_text, "language": "en-US"},
        )

        # THEN expect the response status to be OK
        assert actual_response.status_code == HTTPStatus.OK
        # AND the response content type to be audio/mpeg
        assert actual_response.headers["content-type"] == "audio/mpeg"
        # AND the response body to contain the audio bytes
        assert actual_response.content == given_audio_bytes

    def test_respond_with_status_ok_with_custom_language(self):
        """Test successful synthesis passes the language to the service."""
        # GIVEN a valid text input
        given_text = "Habari"
        # AND an explicit language
        given_language = "sw-KE"
        # AND a service that returns audio bytes
        client, mock_service, _auth = _create_test_client()
        given_audio_bytes = b"fake-audio-content"
        mock_service.synthesize_mock.return_value = given_audio_bytes

        # WHEN the synthesize endpoint is called with the given language
        actual_response = client.post(
            "/text-to-speech/synthesize",
            json={"text": given_text, "language": given_language},
        )

        # THEN expect the response status to be OK
        assert actual_response.status_code == HTTPStatus.OK
        # AND the service to have been called with the given language
        mock_service.synthesize_mock.assert_called_once_with(text=given_text, language_code=given_language)

    def test_respond_with_bad_request_when_text_is_empty(self):
        """Test that empty text is rejected."""
        # GIVEN an empty text input
        client, _mock_service, _auth = _create_test_client()

        # WHEN the synthesize endpoint is called with empty text
        actual_response = client.post(
            "/text-to-speech/synthesize",
            json={"text": "", "language": "en-US"},
        )

        # THEN expect the response status to be BAD_REQUEST
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST

    def test_respond_with_bad_request_when_text_is_whitespace(self):
        """Test that whitespace-only text is rejected."""
        # GIVEN a whitespace-only text input
        client, _mock_service, _auth = _create_test_client()

        # WHEN the synthesize endpoint is called with whitespace text
        actual_response = client.post(
            "/text-to-speech/synthesize",
            json={"text": "   ", "language": "en-US"},
        )

        # THEN expect the response status to be BAD_REQUEST
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST

    def test_respond_with_bad_request_when_text_too_long(self):
        """Test that text exceeding MAX_TEXT_LENGTH is rejected."""
        # GIVEN a text input that exceeds the maximum length
        given_text = "x" * (MAX_TEXT_LENGTH + 1)
        client, _mock_service, _auth = _create_test_client()

        # WHEN the synthesize endpoint is called with the oversized text
        actual_response = client.post(
            "/text-to-speech/synthesize",
            json={"text": given_text, "language": "en-US"},
        )

        # THEN expect the response status to be BAD_REQUEST
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST

    def test_respond_with_unprocessable_entity_when_no_audio_returned(self):
        """Test that empty synthesis results return 422."""
        # GIVEN a valid text input
        given_text = "Hello world"
        # AND a service that raises EmptySynthesisError
        client, mock_service, _auth = _create_test_client()
        mock_service.synthesize_mock.side_effect = EmptySynthesisError()

        # WHEN the synthesize endpoint is called
        actual_response = client.post(
            "/text-to-speech/synthesize",
            json={"text": given_text, "language": "en-US"},
        )

        # THEN expect the response status to be UNPROCESSABLE_ENTITY
        assert actual_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_respond_with_bad_gateway_when_service_fails(self):
        """Test that Google TTS API failures return 502."""
        # GIVEN a valid text input
        given_text = "Hello world"
        # AND a service that raises TextToSpeechServiceError
        client, mock_service, _auth = _create_test_client()
        mock_service.synthesize_mock.side_effect = TextToSpeechServiceError(detail="API unavailable")

        # WHEN the synthesize endpoint is called
        actual_response = client.post(
            "/text-to-speech/synthesize",
            json={"text": given_text, "language": "en-US"},
        )

        # THEN expect the response status to be BAD_GATEWAY
        assert actual_response.status_code == HTTPStatus.BAD_GATEWAY

    def test_respond_with_internal_error_on_unexpected_exception(self):
        """Test that unexpected errors return 500."""
        # GIVEN a valid text input
        given_text = "Hello world"
        # AND a service that raises an unexpected error
        client, mock_service, _auth = _create_test_client()
        mock_service.synthesize_mock.side_effect = RuntimeError("something broke")

        # WHEN the synthesize endpoint is called
        actual_response = client.post(
            "/text-to-speech/synthesize",
            json={"text": given_text, "language": "en-US"},
        )

        # THEN expect the response status to be INTERNAL_SERVER_ERROR
        assert actual_response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_respond_with_unauthorized_when_not_authenticated(self):
        """Test that unauthenticated requests are rejected."""
        # GIVEN an unauthenticated user
        client, _mock_service, _auth = _create_test_client(auth=UnauthenticatedMockAuth())

        # WHEN the synthesize endpoint is called
        actual_response = client.post(
            "/text-to-speech/synthesize",
            json={"text": "Hello world", "language": "en-US"},
        )

        # THEN expect the response status to be UNAUTHORIZED
        assert actual_response.status_code == HTTPStatus.UNAUTHORIZED
