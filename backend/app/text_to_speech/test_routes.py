from http import HTTPStatus
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rate_limiter import ClientRateLimiter
from app.i18n.types import Locale
from app.text_to_speech import routes as text_to_speech_routes
from app.text_to_speech.adapter import GeminiTextToSpeechAdapter
from app.text_to_speech.errors import EmptySynthesisError, LocaleNotEnabledError, TextToSpeechServiceError
from app.text_to_speech.routes import (add_text_to_speech_routes, get_text_to_speech_config,
                                       get_text_to_speech_rate_limiter, get_text_to_speech_service)
from app.text_to_speech.service import ITextToSpeechService, TextToSpeechService
from app.text_to_speech.types import SynthesizedAudio, TextToSpeechConfig
from common_libs.test_utilities.mock_auth import MockAuth, UnauthenticatedMockAuth

_GIVEN_AUDIO = b"ID3-mp3-audio"
_GIVEN_LOCALE = Locale.EN_US
_GIVEN_MAX_TEXT_BYTES = 20


def _given_config(*, enabled: bool = True, rate_limit_per_minute: int = 100) -> TextToSpeechConfig:
    return TextToSpeechConfig.model_validate({
        "enabled": enabled,
        "maxTextBytes": _GIVEN_MAX_TEXT_BYTES,
        "rateLimitPerMinute": rate_limit_per_minute,
        "locales": {_GIVEN_LOCALE.value: {"enabled": True, "voice": "Kore", "style": "warm"}},
    })


class _FakeService(ITextToSpeechService):
    def __init__(self):
        self.error: Exception | None = None
        self.calls: list[tuple[str, Locale]] = []

    async def synthesize(self, *, text, locale):
        self.calls.append((text, locale))
        if self.error is not None:
            raise self.error
        return SynthesizedAudio(content=_GIVEN_AUDIO, media_type="audio/mpeg", locale=locale)


def _given_client(*, config: TextToSpeechConfig, service: ITextToSpeechService,
                  auth: MockAuth | None = None) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_text_to_speech_config] = lambda: config
    app.dependency_overrides[get_text_to_speech_service] = lambda: service
    rate_limiter = ClientRateLimiter(config.rate_limit_per_minute)
    app.dependency_overrides[get_text_to_speech_rate_limiter] = lambda: rate_limiter
    add_text_to_speech_routes(app, auth or MockAuth(), config)
    return TestClient(app)


@pytest.fixture
def fake_service() -> _FakeService:
    return _FakeService()


@pytest.fixture
def client(fake_service) -> TestClient:
    return _given_client(config=_given_config(), service=fake_service)


class TestSynthesizeRoute:
    def test_returns_the_audio_as_mp3(self, client, fake_service):
        # GIVEN a text in an enabled locale, with surrounding whitespace
        given_text = "Hello there."
        given_body = {"text": f"  {given_text}  ", "locale": _GIVEN_LOCALE.value}

        # WHEN the text is sent to be read aloud
        actual_response = client.post("/text-to-speech/synthesize", json=given_body)

        # THEN expect OK with the MP3 audio
        expected_media_type = "audio/mpeg"
        assert actual_response.status_code == HTTPStatus.OK
        assert actual_response.headers["content-type"] == expected_media_type
        assert actual_response.content == _GIVEN_AUDIO
        # AND the service to have been asked for the trimmed text in the locale
        assert fake_service.calls == [(given_text, _GIVEN_LOCALE)]

    @pytest.mark.parametrize("given_text", ["", "   \n\t"], ids=["empty", "whitespace only"])
    def test_rejects_an_empty_text_with_bad_request(self, client, fake_service, given_text):
        # WHEN an empty text is sent
        actual_response = client.post("/text-to-speech/synthesize", json={"text": given_text, "locale": _GIVEN_LOCALE.value})

        # THEN expect BAD REQUEST
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        # AND the service not to have been called
        assert fake_service.calls == []

    def test_rejects_a_text_longer_than_the_limit_with_bad_request(self, client, fake_service):
        # GIVEN a text one byte over the limit
        given_text = "a" * (_GIVEN_MAX_TEXT_BYTES + 1)

        # WHEN it is sent
        actual_response = client.post("/text-to-speech/synthesize", json={"text": given_text, "locale": _GIVEN_LOCALE.value})

        # THEN expect BAD REQUEST
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        assert fake_service.calls == []

    def test_counts_the_limit_in_bytes(self, client, fake_service):
        # GIVEN a text within the limit in characters, but over it in bytes of UTF-8
        given_text = "é" * (_GIVEN_MAX_TEXT_BYTES // 2 + 1)

        # WHEN it is sent
        actual_response = client.post("/text-to-speech/synthesize", json={"text": given_text, "locale": _GIVEN_LOCALE.value})

        # THEN expect BAD REQUEST
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST

    def test_accepts_a_text_exactly_at_the_limit(self, client):
        # GIVEN a text exactly at the limit
        given_text = "a" * _GIVEN_MAX_TEXT_BYTES

        # WHEN it is sent
        actual_response = client.post("/text-to-speech/synthesize", json={"text": given_text, "locale": _GIVEN_LOCALE.value})

        # THEN expect OK
        assert actual_response.status_code == HTTPStatus.OK

    @pytest.mark.parametrize("given_body", [
        {"text": "Hello"},
        {"text": "Hello", "locale": "xx-YY"},
        {"locale": _GIVEN_LOCALE.value},
        {"text": "Hello", "locale": _GIVEN_LOCALE.value, "voice": "Puck"},
    ], ids=["missing locale", "unknown locale", "missing text", "unknown field"])
    def test_rejects_an_invalid_body_by_validation(self, client, fake_service, given_body):
        # WHEN an invalid body is sent
        actual_response = client.post("/text-to-speech/synthesize", json=given_body)

        # THEN expect UNPROCESSABLE ENTITY
        assert actual_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert fake_service.calls == []

    @pytest.mark.parametrize("given_error, expected_status", [
        (LocaleNotEnabledError(Locale.EN_GB), HTTPStatus.BAD_REQUEST),
        (EmptySynthesisError("no audio"), HTTPStatus.UNPROCESSABLE_ENTITY),
        (TextToSpeechServiceError("upstream"), HTTPStatus.BAD_GATEWAY),
        (RuntimeError("unexpected"), HTTPStatus.INTERNAL_SERVER_ERROR),
    ], ids=["locale not enabled", "no audio", "upstream failure", "unexpected error"])
    def test_maps_the_service_errors_to_status_codes(self, client, fake_service, given_error, expected_status):
        # GIVEN the service fails
        fake_service.error = given_error

        # WHEN a text is sent
        actual_response = client.post("/text-to-speech/synthesize", json={"text": "Hello", "locale": "en-GB"})

        # THEN expect the status of the failure
        assert actual_response.status_code == expected_status

    def test_rejects_a_user_over_the_rate_limit(self, fake_service):
        # GIVEN a limit of texts per minute
        given_limit = 2
        given_client = _given_client(config=_given_config(rate_limit_per_minute=given_limit), service=fake_service)
        given_body = {"text": "Hello", "locale": _GIVEN_LOCALE.value}

        # WHEN the user sends three texts
        actual_statuses = [given_client.post("/text-to-speech/synthesize", json=given_body).status_code
                           for _ in range(given_limit + 1)]

        # THEN expect the third to be refused with TOO MANY REQUESTS
        assert actual_statuses == [HTTPStatus.OK] * given_limit + [HTTPStatus.TOO_MANY_REQUESTS]
        # AND the service to have been called twice only
        assert len(fake_service.calls) == given_limit

    def test_lets_the_user_in_again_in_the_next_window(self, fake_service):
        # GIVEN a user who reached the limit of one text per minute
        given_client = _given_client(config=_given_config(rate_limit_per_minute=1), service=fake_service)
        given_body = {"text": "Hello", "locale": _GIVEN_LOCALE.value}
        given_now = 1000.0
        with patch("app.gateway.rate_limiter.time.monotonic", return_value=given_now):
            given_client.post("/text-to-speech/synthesize", json=given_body)
            given_limited_status = given_client.post("/text-to-speech/synthesize", json=given_body).status_code

        # WHEN the user sends a text a minute later
        with patch("app.gateway.rate_limiter.time.monotonic", return_value=given_now + 60):
            actual_response = given_client.post("/text-to-speech/synthesize", json=given_body)

        # THEN expect the user to have been limited
        assert given_limited_status == HTTPStatus.TOO_MANY_REQUESTS
        # AND to be let in again
        assert actual_response.status_code == HTTPStatus.OK

    def test_rejects_an_unauthenticated_request(self, fake_service):
        # GIVEN the user is not authenticated
        given_client = _given_client(config=_given_config(), service=fake_service, auth=UnauthenticatedMockAuth())

        # WHEN a text is sent
        actual_response = given_client.post("/text-to-speech/synthesize", json={"text": "Hello", "locale": _GIVEN_LOCALE.value})

        # THEN expect UNAUTHORIZED
        assert actual_response.status_code == HTTPStatus.UNAUTHORIZED
        assert fake_service.calls == []

    def test_adds_no_route_when_read_aloud_is_off(self, fake_service):
        # GIVEN read aloud is off
        given_client = _given_client(config=_given_config(enabled=False), service=fake_service)

        # WHEN a text is sent
        actual_response = given_client.post("/text-to-speech/synthesize", json={"text": "Hello", "locale": _GIVEN_LOCALE.value})

        # THEN expect NOT FOUND
        assert actual_response.status_code == HTTPStatus.NOT_FOUND


class TestTextToSpeechWiring:
    @pytest.fixture(autouse=True)
    def reset_singletons(self) -> Generator[None, None, None]:
        text_to_speech_routes._service_singleton = None
        text_to_speech_routes._rate_limiter_singleton = None
        yield
        text_to_speech_routes._service_singleton = None
        text_to_speech_routes._rate_limiter_singleton = None

    @pytest.mark.asyncio
    async def test_builds_the_service_with_the_gemini_adapter_once(self):
        # GIVEN read aloud is on
        given_config = _given_config()

        # WHEN the service is asked for twice
        with patch("app.text_to_speech.adapter.get_genai_client") as mocked_get_client:
            actual_first = await get_text_to_speech_service(given_config)
            actual_second = await get_text_to_speech_service(given_config)

        # THEN expect one service, built with the Gemini adapter for the configured model
        assert actual_first is actual_second
        assert isinstance(actual_first, TextToSpeechService)
        actual_adapter = actual_first._adapter  # pylint: disable=protected-access
        assert isinstance(actual_adapter, GeminiTextToSpeechAdapter)
        assert actual_adapter._model == given_config.model  # pylint: disable=protected-access
        # AND no Google client yet: the shared Vertex AI client is got when a text is first read
        mocked_get_client.assert_not_called()

    def test_builds_one_rate_limiter(self):
        # WHEN the rate limiter is asked for twice
        actual_first = get_text_to_speech_rate_limiter(_given_config())
        actual_second = get_text_to_speech_rate_limiter(_given_config())

        # THEN expect the same one
        assert actual_first is actual_second

    def test_builds_nothing_when_read_aloud_is_off(self):
        # GIVEN read aloud is off
        app = FastAPI()

        # WHEN the routes are added
        with patch("app.text_to_speech.adapter.get_genai_client") as mocked_get_client:
            add_text_to_speech_routes(app, MockAuth(), _given_config(enabled=False))

        # THEN expect no route
        assert not any(getattr(route, "path", "").startswith("/text-to-speech") for route in app.routes)
        # AND no service or Google client
        assert text_to_speech_routes._service_singleton is None
        mocked_get_client.assert_not_called()
