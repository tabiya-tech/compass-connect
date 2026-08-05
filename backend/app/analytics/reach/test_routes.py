"""
Tests for the reach analytics route.

Reach is a server-to-server endpoint protected by ApiKeyAuth (x-api-key header
presence; the API Gateway validates the actual key), the same pattern as the esco
search routes. Institution scope is passed explicitly via the `institution` param.
"""
import base64
from http import HTTPStatus
from typing import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, FastAPI
from starlette.testclient import TestClient

from app.analytics.reach.repository import ReachRepository, get_reach_repository
from app.analytics.reach.routes import add_reach_routes

TestClientWithMocks = tuple[TestClient, ReachRepository]

_REACH_PARAMS = "start_date=2026-01-01&end_date=2026-01-03"
_API_KEY_HEADER = {"x-api-key": "some-key"}

_GIVEN_REACH = {
    "summary": {
        "total_users": 5000,
        "active_users_30d": 1200,
        "total_logins": 0,
        "avg_logins_per_user": 0.0,
        "avg_session_minutes": 0,
    },
    "series": [
        {"label": "2026-01-01", "cumulative": 400, "added": 400, "new_users": 400, "returning": 300, "logins": 0},
        {"label": "2026-01-02", "cumulative": 650, "added": 250, "new_users": 250, "returning": 280, "logins": 0},
    ],
}


def _encode_institution_id(name: str) -> str:
    return base64.urlsafe_b64encode(name.encode()).decode().rstrip("=")


@pytest.fixture(scope="function")
def client_with_mocks() -> Generator[TestClientWithMocks, None, None]:
    mocked_repository = AsyncMock(spec=ReachRepository)

    app = FastAPI()
    app.dependency_overrides[get_reach_repository] = lambda: mocked_repository

    router = APIRouter(prefix="/analytics", tags=["analytics"])
    add_reach_routes(router)
    app.include_router(router)

    yield TestClient(app, raise_server_exceptions=False), mocked_repository


class TestGetReach:
    def test_returns_200_with_composed_reach_when_api_key_present(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_reach = AsyncMock(return_value=_GIVEN_REACH)

        # WHEN the endpoint is called with a valid x-api-key header
        actual_response = client.get(f"/analytics/reach?{_REACH_PARAMS}", headers=_API_KEY_HEADER)

        # THEN the response is OK and matches the composed summary + series
        assert actual_response.status_code == HTTPStatus.OK
        body = actual_response.json()
        assert body["summary"]["total_users"] == 5000
        assert body["summary"]["active_users_30d"] == 1200
        assert len(body["series"]) == 2
        assert body["series"][1]["cumulative"] == 650
        # AND no institution scope was applied (all institutions)
        assert mocked_repository.get_reach.call_args.kwargs["institution_name"] is None

    def test_returns_403_when_no_api_key(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_reach = AsyncMock()

        # WHEN the endpoint is called without the x-api-key header
        actual_response = client.get(f"/analytics/reach?{_REACH_PARAMS}")

        # THEN access is rejected (ApiKeyAuth's APIKeyHeader auto_error) and the repository is not called
        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        mocked_repository.get_reach.assert_not_called()

    def test_scopes_to_institution_when_param_given(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_reach = AsyncMock(return_value=_GIVEN_REACH)
        institution = _encode_institution_id("Test School")

        # WHEN an institution id is passed
        actual_response = client.get(
            f"/analytics/reach?{_REACH_PARAMS}&institution={institution}", headers=_API_KEY_HEADER
        )

        # THEN the repository is scoped to that decoded institution name
        assert actual_response.status_code == HTTPStatus.OK
        assert mocked_repository.get_reach.call_args.kwargs["institution_name"] == "Test School"

    def test_returns_400_when_start_after_end(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_reach = AsyncMock()

        # WHEN start_date is after end_date
        actual_response = client.get(
            "/analytics/reach?start_date=2026-02-01&end_date=2026-01-01", headers=_API_KEY_HEADER
        )

        # THEN the response is BAD REQUEST and the repository is not called
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        mocked_repository.get_reach.assert_not_called()

    def test_returns_400_for_invalid_granularity(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_reach = AsyncMock()

        # WHEN an invalid granularity is passed
        actual_response = client.get(
            f"/analytics/reach?{_REACH_PARAMS}&granularity=year", headers=_API_KEY_HEADER
        )

        # THEN the response is BAD REQUEST
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        mocked_repository.get_reach.assert_not_called()

    def test_returns_500_when_repository_raises(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_reach = AsyncMock(side_effect=Exception("db down"))

        # WHEN the endpoint is called and the repository raises
        actual_response = client.get(f"/analytics/reach?{_REACH_PARAMS}", headers=_API_KEY_HEADER)

        # THEN the response is INTERNAL SERVER ERROR
        assert actual_response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
