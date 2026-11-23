from http import HTTPStatus
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rate_limiter import ClientRateLimiter
from app.i18n.types import Locale
from app.speech_to_text import routes as speech_to_text_routes
from app.speech_to_text.adapter import ChirpSpeechToTextAdapter
from app.speech_to_text.errors import EmptyTranscriptionError, LocaleNotEnabledError, SpeechToTextServiceError
from app.speech_to_text.routes import (MAX_MULTIPART_OVERHEAD_BYTES, add_speech_to_text_routes,
                                       get_speech_to_text_config, get_speech_to_text_rate_limiter,
                                       get_speech_to_text_service)
from app.speech_to_text.service import ISpeechToTextService, SpeechToTextService
from app.speech_to_text.types import AudioUpload, SpeechToTextConfig, Transcription
from common_libs.test_utilities.mock_auth import MockAuth, UnauthenticatedMockAuth

_FIXTURES = Path(__file__).parent / "test_fixtures"
_GIVEN_WEBM_RECORDING = (_FIXTURES / "en-US-carpenter.webm").read_bytes()
_GIVEN_MP4_RECORDING = (_FIXTURES / "en-US-carpenter.mp4").read_bytes()
_GIVEN_TRANSCRIPT = "I worked as a carpenter for three years."
_GIVEN_LOCALE = Locale.EN_US
_GIVEN_MAX_AUDIO_BYTES = 20 * 1024


def _given_config(*, enabled: bool = True, rate_limit_per_minute: int = 100) -> SpeechToTextConfig:
    return SpeechToTextConfig.model_validate({
        "enabled": enabled,
        "maxAudioBytes": _GIVEN_MAX_AUDIO_BYTES,
        "rateLimitPerMinute": rate_limit_per_minute,
        "locales": [_GIVEN_LOCALE.value],
    })


class _FakeService(ISpeechToTextService):
    def __init__(self):
        self.error: Exception | None = None
        self.calls: list[tuple[AudioUpload, Locale]] = []

    async def transcribe(self, *, audio, locale):
        self.calls.append((audio, locale))
        if self.error is not None:
            raise self.error
        return Transcription(text=_GIVEN_TRANSCRIPT, locale=locale)


def _given_client(*, config: SpeechToTextConfig, service: ISpeechToTextService,
                  auth: MockAuth | None = None) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_speech_to_text_config] = lambda: config
    app.dependency_overrides[get_speech_to_text_service] = lambda: service
    rate_limiter = ClientRateLimiter(config.rate_limit_per_minute)
    app.dependency_overrides[get_speech_to_text_rate_limiter] = lambda: rate_limiter
    add_speech_to_text_routes(app, auth or MockAuth(), config)
    return TestClient(app)


def _transcribe(client: TestClient, *, content: bytes = _GIVEN_WEBM_RECORDING, content_type: str = "audio/webm",
                locale: str | None = _GIVEN_LOCALE.value, headers: dict[str, str] | None = None):
    data = {"locale": locale} if locale is not None else {}
    return client.post("/speech-to-text/transcribe", files={"audio": ("recording", content, content_type)},
                       data=data, headers=headers)


@pytest.fixture
def fake_service() -> _FakeService:
    return _FakeService()


@pytest.fixture
def client(fake_service) -> TestClient:
    return _given_client(config=_given_config(), service=fake_service)


class TestTranscribeRoute:
    @pytest.mark.parametrize("given_content, given_content_type, expected_mime_type", [
        (_GIVEN_WEBM_RECORDING, "audio/webm;codecs=opus", "audio/webm"),
        (_GIVEN_MP4_RECORDING, "audio/mp4", "audio/mp4"),
    ], ids=["Chrome and Firefox webm/opus", "Safari mp4/aac"])
    def test_returns_the_transcript_of_a_browser_recording(self, client, fake_service, given_content,
                                                           given_content_type, expected_mime_type):
        # WHEN a recording made by a browser is uploaded
        actual_response = _transcribe(client, content=given_content, content_type=given_content_type)

        # THEN expect OK with the transcript and the locale
        assert actual_response.status_code == HTTPStatus.OK
        assert actual_response.json() == {"text": _GIVEN_TRANSCRIPT, "locale": _GIVEN_LOCALE.value}
        # AND the service to have been asked once for the recording, with its media type without parameters
        assert fake_service.calls == [(AudioUpload(content=given_content, mime_type=expected_mime_type), _GIVEN_LOCALE)]

    @pytest.mark.parametrize("given_content_type, expected_mime_type", [
        ("Audio/WebM ; codecs=opus", "audio/webm"),
        (" audio/webm;codecs=\"opus\" ", "audio/webm"),
    ], ids=["mixed case and spaces", "quoted parameter"])
    def test_accepts_a_media_type_with_parameters_and_odd_spacing(self, client, fake_service, given_content_type,
                                                                   expected_mime_type):
        # WHEN a recording with an unusually written media type is uploaded
        actual_response = _transcribe(client, content_type=given_content_type)

        # THEN expect OK
        assert actual_response.status_code == HTTPStatus.OK
        assert fake_service.calls[0][0].mime_type == expected_mime_type

    @pytest.mark.parametrize("given_content_type", ["text/plain", "application/octet-stream", "image/png"])
    def test_rejects_an_unsupported_media_type(self, client, fake_service, given_content_type):
        # WHEN a file that is not a supported recording is uploaded
        actual_response = _transcribe(client, content_type=given_content_type)

        # THEN expect UNSUPPORTED MEDIA TYPE
        assert actual_response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert fake_service.calls == []

    def test_rejects_an_empty_recording(self, client, fake_service):
        # WHEN an empty recording is uploaded
        actual_response = _transcribe(client, content=b"")

        # THEN expect BAD REQUEST
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        assert fake_service.calls == []

    def test_rejects_a_request_without_a_recording(self, client, fake_service):
        # WHEN a request without a recording is sent
        actual_response = client.post("/speech-to-text/transcribe", data={"locale": _GIVEN_LOCALE.value})

        # THEN expect UNPROCESSABLE ENTITY
        assert actual_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert fake_service.calls == []

    def test_rejects_a_recording_larger_than_the_limit(self, client, fake_service):
        # WHEN a recording one byte over the limit is uploaded
        actual_response = _transcribe(client, content=b"a" * (_GIVEN_MAX_AUDIO_BYTES + 1))

        # THEN expect REQUEST ENTITY TOO LARGE
        assert actual_response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        assert fake_service.calls == []

    def test_rejects_an_oversized_upload_from_its_header(self, client, fake_service):
        # GIVEN a request whose Content-Length is over the limit and the multipart margin
        given_headers = {"content-length": str(_GIVEN_MAX_AUDIO_BYTES + MAX_MULTIPART_OVERHEAD_BYTES + 1)}

        # WHEN it is sent
        actual_response = _transcribe(client, content=b"small", headers=given_headers)

        # THEN expect REQUEST ENTITY TOO LARGE
        assert actual_response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        assert fake_service.calls == []

    @pytest.mark.parametrize("given_locale", [None, "xx-YY", "ny-ZM"], ids=["missing", "unknown", "frontend only"])
    def test_rejects_a_missing_or_unknown_locale_by_validation(self, client, fake_service, given_locale):
        # WHEN a recording is uploaded without a known locale
        actual_response = _transcribe(client, locale=given_locale)

        # THEN expect UNPROCESSABLE ENTITY
        assert actual_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert fake_service.calls == []

    @pytest.mark.parametrize("given_error, expected_status", [
        (LocaleNotEnabledError(_GIVEN_LOCALE), HTTPStatus.BAD_REQUEST),
        (EmptyTranscriptionError("no speech"), HTTPStatus.UNPROCESSABLE_ENTITY),
        (SpeechToTextServiceError("upstream"), HTTPStatus.BAD_GATEWAY),
        (RuntimeError("unexpected"), HTTPStatus.INTERNAL_SERVER_ERROR),
    ], ids=["locale not enabled", "no speech", "upstream failure", "unexpected error"])
    def test_maps_the_service_errors_to_status_codes(self, client, fake_service, given_error, expected_status):
        # GIVEN the service fails
        fake_service.error = given_error

        # WHEN a recording is uploaded
        actual_response = _transcribe(client)

        # THEN expect the status of the failure
        assert actual_response.status_code == expected_status

    def test_rejects_a_user_over_the_rate_limit(self, fake_service):
        # GIVEN a limit of recordings per minute
        given_limit = 2
        given_client = _given_client(config=_given_config(rate_limit_per_minute=given_limit), service=fake_service)

        # WHEN the user uploads three recordings
        actual_statuses = [_transcribe(given_client).status_code for _ in range(given_limit + 1)]

        # THEN expect the third to be refused with TOO MANY REQUESTS
        assert actual_statuses == [HTTPStatus.OK] * given_limit + [HTTPStatus.TOO_MANY_REQUESTS]
        # AND the service to have been called twice only
        assert len(fake_service.calls) == given_limit

    def test_lets_the_user_in_again_in_the_next_window(self, fake_service):
        # GIVEN a user who reached the limit of one recording per minute
        given_client = _given_client(config=_given_config(rate_limit_per_minute=1), service=fake_service)
        given_now = 1000.0
        with patch("app.gateway.rate_limiter.time.monotonic", return_value=given_now):
            _transcribe(given_client)
            given_limited_status = _transcribe(given_client).status_code

        # WHEN the user uploads a recording a minute later
        with patch("app.gateway.rate_limiter.time.monotonic", return_value=given_now + 60):
            actual_response = _transcribe(given_client)

        # THEN expect the user to have been limited
        assert given_limited_status == HTTPStatus.TOO_MANY_REQUESTS
        # AND to be let in again
        assert actual_response.status_code == HTTPStatus.OK

    def test_rejects_an_unauthenticated_request(self, fake_service):
        # GIVEN the user is not authenticated
        given_client = _given_client(config=_given_config(), service=fake_service, auth=UnauthenticatedMockAuth())

        # WHEN a recording is uploaded
        actual_response = _transcribe(given_client)

        # THEN expect UNAUTHORIZED
        assert actual_response.status_code == HTTPStatus.UNAUTHORIZED
        assert fake_service.calls == []

    def test_adds_no_route_when_voice_input_is_off(self, fake_service):
        # GIVEN voice input is off
        given_client = _given_client(config=_given_config(enabled=False), service=fake_service)

        # WHEN a recording is uploaded
        actual_response = _transcribe(given_client)

        # THEN expect NOT FOUND
        assert actual_response.status_code == HTTPStatus.NOT_FOUND


class TestSpeechToTextWiring:
    @pytest.fixture(autouse=True)
    def reset_singletons(self) -> Generator[None, None, None]:
        speech_to_text_routes._service_singleton = None
        speech_to_text_routes._rate_limiter_singleton = None
        yield
        speech_to_text_routes._service_singleton = None
        speech_to_text_routes._rate_limiter_singleton = None

    @pytest.mark.asyncio
    async def test_builds_the_service_with_the_chirp_adapter_once(self):
        # GIVEN voice input is on
        given_config = _given_config()
        # AND the project of the Google credentials
        given_project_id = "my-project"

        # WHEN the service is asked for twice
        with patch("app.speech_to_text.adapter.SpeechClient") as mocked_client_class, \
                patch("app.speech_to_text.routes.google.auth.default", return_value=(None, given_project_id)):
            actual_first = await get_speech_to_text_service(given_config)
            actual_second = await get_speech_to_text_service(given_config)

        # THEN expect one service, built with the Chirp adapter for the project of the credentials
        assert actual_first is actual_second
        assert isinstance(actual_first, SpeechToTextService)
        actual_adapter = actual_first._adapter  # pylint: disable=protected-access
        assert isinstance(actual_adapter, ChirpSpeechToTextAdapter)
        assert actual_adapter._recognizer.startswith(f"projects/{given_project_id}/")  # pylint: disable=protected-access
        # AND one Google client
        mocked_client_class.assert_called_once()

    def test_builds_one_rate_limiter(self):
        # WHEN the rate limiter is asked for twice
        actual_first = get_speech_to_text_rate_limiter(_given_config())
        actual_second = get_speech_to_text_rate_limiter(_given_config())

        # THEN expect the same one
        assert actual_first is actual_second

    def test_builds_nothing_when_voice_input_is_off(self):
        # GIVEN voice input is off
        app = FastAPI()

        # WHEN the routes are added
        with patch("app.speech_to_text.adapter.SpeechClient") as mocked_client_class:
            add_speech_to_text_routes(app, MockAuth(), _given_config(enabled=False))

        # THEN expect no route
        assert not any(getattr(route, "path", "").startswith("/speech-to-text") for route in app.routes)
        # AND no service or Google client
        assert speech_to_text_routes._service_singleton is None
        mocked_client_class.assert_not_called()
