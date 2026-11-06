import logging
from http import HTTPStatus
from typing import Any, Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.app_config import ApplicationConfig, set_application_config
from app.channels.routes import add_channels_routes, get_channel_gateway_service, ChannelUserIdRedactionFilter
from app.channels.service import IChannelGatewayService, ChannelUserNotFoundError, HELLO_WORLD_MESSAGE
from app.channels.types import Channel, OutgoingMessage
from app.errors.handlers import register_exception_handlers

_API_KEY = "test-api-key"
_CHANNEL_USER_ID = "100200300"


@pytest.fixture(scope="function")
def mocked_service() -> AsyncMock:
    return AsyncMock(spec=IChannelGatewayService)


def _build_client(config: ApplicationConfig, mocked_service: AsyncMock) -> TestClient:
    set_application_config(config)
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_channel_gateway_service] = lambda: mocked_service
    add_channels_routes(app)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="function")
def direct_ingress(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INGRESS_MODE", "direct")
    monkeypatch.setenv("TARGET_ENVIRONMENT_TYPE", "prod")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "test-project")


@pytest.fixture(scope="function")
def client(setup_application_config: ApplicationConfig, mocked_service: AsyncMock, direct_ingress,
           monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, Any, None]:
    monkeypatch.setenv("API_KEYS", _API_KEY)
    yield _build_client(setup_application_config, mocked_service)


def _post_initialize(client: TestClient, body: dict, api_key: str | None = _API_KEY):
    headers = {"x-api-key": api_key} if api_key is not None else {}
    return client.post("/api/channels/conversations", json=body, headers=headers)


def _post_message(client: TestClient, body: dict, channel_user_id: str = _CHANNEL_USER_ID,
                  api_key: str | None = _API_KEY):
    headers = {"x-api-key": api_key} if api_key is not None else {}
    return client.post(f"/api/channels/conversations/{channel_user_id}/messages", json=body, headers=headers)


class TestInitializeConversationRoute:
    def test_returns_the_messages_of_the_service(self, client: TestClient, mocked_service: AsyncMock):
        # GIVEN the service returns the welcome message
        given_messages = [OutgoingMessage(text="Welcome")]
        mocked_service.initialize_conversation.return_value = given_messages

        # WHEN the bot initializes the conversation of a Telegram user
        actual = _post_initialize(client, {"channel": "telegram", "channel_user_id": _CHANNEL_USER_ID})

        # THEN the response is OK with the messages
        assert actual.status_code == HTTPStatus.OK
        assert actual.json() == [m.model_dump() for m in given_messages]
        # AND the service got the channel and the channel user id
        mocked_service.initialize_conversation.assert_awaited_once_with(Channel.TELEGRAM, _CHANNEL_USER_ID)

    @pytest.mark.parametrize("given_body", [
        pytest.param({"channel_user_id": _CHANNEL_USER_ID}, id="missing channel"),
        pytest.param({"channel": "telegram"}, id="missing channel_user_id"),
        pytest.param({"channel": "web-app", "channel_user_id": _CHANNEL_USER_ID}, id="web-app is not a bot channel"),
        pytest.param({"channel": "sms", "channel_user_id": _CHANNEL_USER_ID}, id="unknown channel"),
        pytest.param({"channel": "telegram", "channel_user_id": ""}, id="empty channel_user_id"),
        pytest.param({"channel": "telegram", "channel_user_id": "x" * 129}, id="channel_user_id too long"),
        pytest.param({"channel": "telegram", "channel_user_id": "a/b"}, id="channel_user_id with a slash"),
        pytest.param({"channel": "telegram", "channel_user_id": ".."}, id="channel_user_id is a dot segment"),
        pytest.param({"channel": "telegram", "channel_user_id": _CHANNEL_USER_ID, "foo": "bar"}, id="extra field"),
    ])
    def test_invalid_body_is_422(self, client: TestClient, mocked_service: AsyncMock, given_body: dict):
        # WHEN the bot sends an invalid body
        actual = _post_initialize(client, given_body)

        # THEN the response is UNPROCESSABLE ENTITY
        assert actual.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        # AND the service is not called
        mocked_service.initialize_conversation.assert_not_called()

    def test_whatsapp_phone_number_is_a_valid_channel_user_id(self, client: TestClient, mocked_service: AsyncMock):
        # GIVEN the service returns a message
        mocked_service.initialize_conversation.return_value = [OutgoingMessage(text="Welcome")]

        # WHEN the bot initializes the conversation of a WhatsApp user
        actual = _post_initialize(client, {"channel": "whatsapp", "channel_user_id": "+250788000000"})

        # THEN the response is OK
        assert actual.status_code == HTTPStatus.OK

    def test_unexpected_error_is_500(self, client: TestClient, mocked_service: AsyncMock):
        # GIVEN the service fails
        mocked_service.initialize_conversation.side_effect = Exception("boom")

        # WHEN the bot initializes the conversation of a Telegram user
        actual = _post_initialize(client, {"channel": "telegram", "channel_user_id": _CHANNEL_USER_ID})

        # THEN the response is INTERNAL SERVER ERROR
        assert actual.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


class TestSendMessageRoute:
    def test_returns_hello_world(self, client: TestClient, mocked_service: AsyncMock):
        # GIVEN the service replies "Hello world"
        mocked_service.handle_sent_message.return_value = [OutgoingMessage(text=HELLO_WORLD_MESSAGE)]

        # WHEN the bot sends a message of a Telegram user
        actual = _post_message(client, {"channel": "telegram", "channel_user_id": _CHANNEL_USER_ID, "text": "hi"})

        # THEN the response is OK with "Hello world"
        assert actual.status_code == HTTPStatus.OK
        assert actual.json() == [{"text": HELLO_WORLD_MESSAGE, "choices": [], "document": None}]
        # AND the service got the message
        actual_message = mocked_service.handle_sent_message.await_args.args[0]
        assert actual_message.channel == Channel.TELEGRAM
        assert actual_message.channel_user_id == _CHANNEL_USER_ID
        assert actual_message.text == "hi"
        assert actual_message.command is None

    def test_channel_user_id_of_the_path_and_body_must_match(self, client: TestClient, mocked_service: AsyncMock):
        # WHEN the bot sends a message with another channel user id in the body than in the path
        actual = _post_message(client, {"channel": "telegram", "channel_user_id": "999", "text": "hi"})

        # THEN the response is UNPROCESSABLE ENTITY
        assert actual.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        # AND the service is not called
        mocked_service.handle_sent_message.assert_not_called()

    @pytest.mark.parametrize("given_body", [
        pytest.param({"channel": "web-app", "channel_user_id": _CHANNEL_USER_ID, "text": "hi"},
                     id="web-app is not a bot channel"),
        pytest.param({"channel": "telegram", "channel_user_id": _CHANNEL_USER_ID, "text": "x" * 1001},
                     id="text too long"),
        pytest.param({"channel": "telegram", "text": "hi"}, id="missing channel_user_id"),
    ])
    def test_invalid_body_is_422(self, client: TestClient, mocked_service: AsyncMock, given_body: dict):
        # WHEN the bot sends an invalid body
        actual = _post_message(client, given_body)

        # THEN the response is UNPROCESSABLE ENTITY
        assert actual.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        # AND the service is not called
        mocked_service.handle_sent_message.assert_not_called()

    def test_unknown_channel_user_is_404(self, client: TestClient, mocked_service: AsyncMock):
        # GIVEN the conversation of the channel user was not initialized
        mocked_service.handle_sent_message.side_effect = ChannelUserNotFoundError()

        # WHEN the bot sends a message of the user
        actual = _post_message(client, {"channel": "telegram", "channel_user_id": _CHANNEL_USER_ID, "text": "hi"})

        # THEN the response is NOT FOUND
        assert actual.status_code == HTTPStatus.NOT_FOUND


class TestApiKey:
    @pytest.mark.parametrize("given_api_key", [
        pytest.param(None, id="missing key"),
        pytest.param("wrong-key", id="wrong key"),
    ])
    def test_both_routes_reject_a_bad_key(self, client: TestClient, mocked_service: AsyncMock,
                                          given_api_key: str | None):
        # WHEN the bot calls the routes without a valid key
        actual_initialize = _post_initialize(client, {"channel": "telegram", "channel_user_id": _CHANNEL_USER_ID},
                                             api_key=given_api_key)
        actual_message = _post_message(client, {"channel": "telegram", "channel_user_id": _CHANNEL_USER_ID,
                                                "text": "hi"}, api_key=given_api_key)

        # THEN both are FORBIDDEN
        assert actual_initialize.status_code == HTTPStatus.FORBIDDEN
        assert actual_message.status_code == HTTPStatus.FORBIDDEN
        # AND the service is not called
        mocked_service.initialize_conversation.assert_not_called()
        mocked_service.handle_sent_message.assert_not_called()

    def test_routes_are_disabled_when_no_key_is_configured(self, setup_application_config: ApplicationConfig,
                                                           mocked_service: AsyncMock, direct_ingress,
                                                           monkeypatch: pytest.MonkeyPatch):
        # GIVEN no API keys are configured
        monkeypatch.setenv("API_KEYS", "")
        given_client = _build_client(setup_application_config, mocked_service)

        # WHEN the bot calls the route with a key
        actual = _post_initialize(given_client, {"channel": "telegram", "channel_user_id": _CHANNEL_USER_ID})

        # THEN the response is FORBIDDEN
        assert actual.status_code == HTTPStatus.FORBIDDEN

    def test_routes_do_not_accept_a_firebase_token(self, client: TestClient, mocked_service: AsyncMock):
        # WHEN the bot calls the route with a bearer token instead of the key
        actual = client.post("/api/channels/conversations",
                             json={"channel": "telegram", "channel_user_id": _CHANNEL_USER_ID},
                             headers={"Authorization": "Bearer some-firebase-token"})

        # THEN the response is FORBIDDEN
        assert actual.status_code == HTTPStatus.FORBIDDEN
        mocked_service.initialize_conversation.assert_not_called()


class TestChannelUserIdRedactionFilter:
    @pytest.mark.parametrize("given_path, expected_path", [
        ("/api/channels/conversations/100200300/messages", "/api/channels/conversations/<redacted>/messages"),
        ("/api/channels/conversations/+250788000000/messages?x=1",
         "/api/channels/conversations/<redacted>/messages?x=1"),
        ("/api/channels/conversations", "/api/channels/conversations"),
        ("/conversations/123/messages", "/conversations/123/messages"),
    ])
    def test_removes_the_channel_user_id_from_access_logs(self, given_path: str, expected_path: str):
        # GIVEN an access log record (client address, method, path, http version, status code)
        given_record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 0,
                                         '%s - "%s %s HTTP/%s" %d', ("1.2.3.4:5", "POST", given_path, "1.1", 200),
                                         None)

        # WHEN the filter is applied
        actual_kept = ChannelUserIdRedactionFilter().filter(given_record)

        # THEN the record is kept, without the channel user id in its path
        assert actual_kept is True
        assert given_record.getMessage() == f'1.2.3.4:5 - "POST {expected_path} HTTP/1.1" 200'
