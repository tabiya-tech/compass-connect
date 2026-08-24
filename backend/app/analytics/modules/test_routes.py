"""Tests for the Build Your Profile module analytics route."""
import base64
from http import HTTPStatus
from typing import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, FastAPI
from starlette.testclient import TestClient

from app.analytics.modules.repository import ModuleAnalyticsRepository, get_module_analytics_repository
from app.analytics.modules.routes import add_module_analytics_routes

TestClientWithMocks = tuple[TestClient, ModuleAnalyticsRepository]

_PARAMS = "start_date=2026-01-01&end_date=2026-01-03"
_API_KEY_HEADER = {"x-api-key": "some-key"}

_GIVEN_BYP = {
    "summary": {
        "started_users": 500,
        "started_percentage": 50.0,
        "completed_users": 300,
        "avg_completion_minutes": 12.5,
    },
    "series": [
        {"label": "2026-01-01", "started": 200, "completed": 120, "skills_reports_generated": 120, "skills_reports_downloaded": 80},
        {"label": "2026-01-02", "started": 300, "completed": 180, "skills_reports_generated": 180, "skills_reports_downloaded": 120},
    ],
    "phases": [
        {"id": "intro", "reached": 500},
        {"id": "experiences", "reached": 420},
        {"id": "skills", "reached": 350},
        {"id": "completed", "reached": 300},
    ],
}


def _encode_institution_id(name: str) -> str:
    return base64.urlsafe_b64encode(name.encode()).decode().rstrip("=")


@pytest.fixture(scope="function")
def client_with_mocks() -> Generator[TestClientWithMocks, None, None]:
    mocked_repository = AsyncMock(spec=ModuleAnalyticsRepository)

    app = FastAPI()
    app.dependency_overrides[get_module_analytics_repository] = lambda: mocked_repository

    router = APIRouter(prefix="/analytics", tags=["analytics"])
    add_module_analytics_routes(router)
    app.include_router(router)

    yield TestClient(app, raise_server_exceptions=False), mocked_repository


class TestGetBuildYourProfile:
    def test_returns_200_with_composed_summary_and_series_when_api_key_present(
        self, client_with_mocks: TestClientWithMocks
    ):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock(return_value=_GIVEN_BYP)

        actual_response = client.get(f"/analytics/modules/build-your-profile?{_PARAMS}", headers=_API_KEY_HEADER)

        assert actual_response.status_code == HTTPStatus.OK
        body = actual_response.json()
        assert body["summary"]["started_users"] == 500
        assert len(body["series"]) == 2
        assert body["series"][1]["completed"] == 180
        assert body["phases"] == [
            {"id": "intro", "reached": 500},
            {"id": "experiences", "reached": 420},
            {"id": "skills", "reached": 350},
            {"id": "completed", "reached": 300},
        ]
        assert mocked_repository.get_build_your_profile.call_args.kwargs["institution_names"] is None

    def test_returns_403_when_no_api_key(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock()

        actual_response = client.get(f"/analytics/modules/build-your-profile?{_PARAMS}")

        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        mocked_repository.get_build_your_profile.assert_not_called()

    def test_scopes_to_multiple_institutions_when_param_given(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock(return_value=_GIVEN_BYP)
        institution_ids = ",".join([_encode_institution_id("Test School"), _encode_institution_id("Other School")])

        actual_response = client.get(
            f"/analytics/modules/build-your-profile?{_PARAMS}&institution_ids={institution_ids}",
            headers=_API_KEY_HEADER,
        )

        assert actual_response.status_code == HTTPStatus.OK
        assert mocked_repository.get_build_your_profile.call_args.kwargs["institution_names"] == [
            "Test School",
            "Other School",
        ]

    def test_forwards_granularity_to_the_repository(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock(return_value=_GIVEN_BYP)

        actual_response = client.get(
            f"/analytics/modules/build-your-profile?{_PARAMS}&granularity=week", headers=_API_KEY_HEADER
        )

        assert actual_response.status_code == HTTPStatus.OK
        assert mocked_repository.get_build_your_profile.call_args.kwargs["granularity"] == "week"

    def test_returns_400_when_start_after_end(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock()

        actual_response = client.get(
            "/analytics/modules/build-your-profile?start_date=2026-02-01&end_date=2026-01-01",
            headers=_API_KEY_HEADER,
        )

        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        mocked_repository.get_build_your_profile.assert_not_called()

    def test_returns_400_for_invalid_granularity(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock()

        actual_response = client.get(
            f"/analytics/modules/build-your-profile?{_PARAMS}&granularity=year", headers=_API_KEY_HEADER
        )

        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        mocked_repository.get_build_your_profile.assert_not_called()

    def test_returns_500_when_repository_raises(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock(side_effect=Exception("db down"))

        actual_response = client.get(f"/analytics/modules/build-your-profile?{_PARAMS}", headers=_API_KEY_HEADER)

        assert actual_response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
