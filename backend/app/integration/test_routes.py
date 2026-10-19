from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.app_config import ApplicationConfig, set_application_config
from app.errors.handlers import register_exception_handlers
from app.integration.routes import add_integration_routes, get_integration_service
from app.integration.service import IntegrationService, ExternalUserConflictError, InvalidHandoffLinkError
from app.integration.types import CreateExternalUserResponse, ExternalUserResponse, HandoffLinkResponse, \
    HandoffAction, ExternalUserConflict, HandoffExchangeResponse

_API_KEY = "test-api-key"
_CREATED_AT = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def _response() -> CreateExternalUserResponse:
    return CreateExternalUserResponse(
        result="User created, hand-off link issued.",
        user=ExternalUserResponse(external_id="ext-1", email="person@example.com", created_at=_CREATED_AT),
        link=HandoffLinkResponse(url="https://compass.example.org/#/handoff?token=abc", expires_at=_CREATED_AT))


@pytest.fixture(scope="function")
def mocked_service() -> AsyncMock:
    return AsyncMock(spec=IntegrationService)


def _build_client(config: ApplicationConfig, mocked_service: AsyncMock) -> TestClient:
    set_application_config(config)
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_integration_service] = lambda: mocked_service
    add_integration_routes(app)
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


def _post_user(client: TestClient, body: dict, api_key: str | None = _API_KEY):
    headers = {"x-api-key": api_key} if api_key is not None else {}
    return client.post("/integration/users", json=body, headers=headers)


class TestCreateUserRoute:
    @pytest.mark.parametrize("given_created, expected_status", [
        (True, HTTPStatus.CREATED),
        (False, HTTPStatus.OK),
    ])
    def test_status_tells_whether_the_user_was_created(self, client: TestClient, mocked_service: AsyncMock,
                                                       given_created: bool, expected_status: HTTPStatus):
        # GIVEN the service creates the user, or finds it
        mocked_service.create_user.return_value = (given_created, _response())

        # WHEN the platform posts a user
        actual = _post_user(client, {"external_id": "ext-1", "email": "person@example.com"})

        # THEN the status says which one, and the body has the user and the link
        assert actual.status_code == expected_status
        assert actual.json()["user"]["external_id"] == "ext-1"
        assert actual.json()["link"]["url"] == "https://compass.example.org/#/handoff?token=abc"

    def test_request_is_normalised_and_defaults_to_skill_report(self, client: TestClient,
                                                                mocked_service: AsyncMock):
        # GIVEN the service creates the user
        mocked_service.create_user.return_value = (True, _response())

        # WHEN the platform posts an email with capitals and spaces, without an action
        _post_user(client, {"external_id": " ext-1 ", "email": " Person@Example.COM "})

        # THEN the service gets the trimmed external id, the lowercase email and the default action
        actual_request = mocked_service.create_user.await_args.args[0]
        assert actual_request.external_id == "ext-1"
        assert actual_request.email == "person@example.com"
        assert actual_request.action == HandoffAction.SKILL_REPORT

    @pytest.mark.parametrize("given_conflict", list(ExternalUserConflict))
    def test_conflicts_are_409_with_an_error_code(self, client: TestClient, mocked_service: AsyncMock,
                                                  given_conflict: ExternalUserConflict):
        # GIVEN the service refuses the user
        mocked_service.create_user.side_effect = ExternalUserConflictError(given_conflict)

        # WHEN the platform posts it
        actual = _post_user(client, {"external_id": "ext-1", "email": "person@example.com"})

        # THEN the response is a 409 with the reason as error code and a description
        assert actual.status_code == HTTPStatus.CONFLICT
        assert actual.json()["error_code"] == given_conflict.value
        assert actual.json()["detail"]

    @pytest.mark.parametrize("given_body", [
        pytest.param({"email": "person@example.com"}, id="missing external_id"),
        pytest.param({"external_id": "ext-1"}, id="missing email"),
        pytest.param({"external_id": "", "email": "person@example.com"}, id="empty external_id"),
        pytest.param({"external_id": "x" * 129, "email": "person@example.com"}, id="external_id too long"),
        pytest.param({"external_id": "ext-1", "email": "not-an-email"}, id="invalid email"),
        pytest.param({"external_id": "ext-1", "email": "person@example.com", "action": "delete_user"},
                     id="unknown action"),
        pytest.param({"external_id": "ext-1", "email": "person@example.com", "gender": "F"},
                     id="unknown field (no personal data beyond the email)"),
    ])
    def test_invalid_body_is_422(self, client: TestClient, mocked_service: AsyncMock, given_body: dict):
        actual = _post_user(client, given_body)
        assert actual.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        mocked_service.create_user.assert_not_called()

    @pytest.mark.parametrize("given_api_key", [None, "wrong-key"])
    def test_missing_or_wrong_api_key_is_rejected(self, client: TestClient, mocked_service: AsyncMock,
                                                  given_api_key: str | None):
        actual = _post_user(client, {"external_id": "ext-1", "email": "person@example.com"}, given_api_key)
        assert actual.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)
        mocked_service.create_user.assert_not_called()


def test_without_api_keys_every_call_is_forbidden(setup_application_config: ApplicationConfig,
                                                  mocked_service: AsyncMock, direct_ingress,
                                                  monkeypatch: pytest.MonkeyPatch):
    # GIVEN an instance without API_KEYS (the integration API is off, like the other API key routes)
    monkeypatch.setenv("API_KEYS", "")
    client = _build_client(setup_application_config, mocked_service)

    # WHEN a platform posts a user with some key
    actual = _post_user(client, {"external_id": "ext-1", "email": "person@example.com"}, "any-key")

    # THEN it is forbidden
    assert actual.status_code == HTTPStatus.FORBIDDEN
    mocked_service.create_user.assert_not_called()


class TestExchangeRoute:
    def test_valid_link(self, client: TestClient, mocked_service: AsyncMock):
        # GIVEN the service accepts the link
        mocked_service.exchange_link.return_value = HandoffExchangeResponse(custom_token="custom-token",  # nosec B106 # test fixture
                                                                            action=HandoffAction.CREATE)

        # WHEN the frontend exchanges it, without credentials
        actual = client.post("/handoff/exchange", json={"token": "abc"})

        # THEN it gets the custom token and the action
        assert actual.status_code == HTTPStatus.OK
        assert actual.json() == {"custom_token": "custom-token", "action": "create"}
        mocked_service.exchange_link.assert_awaited_once_with("abc")

    def test_invalid_link_is_401(self, client: TestClient, mocked_service: AsyncMock):
        mocked_service.exchange_link.side_effect = InvalidHandoffLinkError()
        actual = client.post("/handoff/exchange", json={"token": "abc"})
        assert actual.status_code == HTTPStatus.UNAUTHORIZED

    def test_missing_token_is_422(self, client: TestClient, mocked_service: AsyncMock):
        actual = client.post("/handoff/exchange", json={})
        assert actual.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        mocked_service.exchange_link.assert_not_called()
