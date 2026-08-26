"""Tests for the demographics analytics route."""
import base64
from http import HTTPStatus
from typing import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, FastAPI
from starlette.testclient import TestClient

from app.analytics.demographics.repository import DemographicsRepository, get_demographics_repository
from app.analytics.demographics.routes import add_demographics_routes

TestClientWithMocks = tuple[TestClient, DemographicsRepository]

_API_KEY_HEADER = {"x-api-key": "some-key"}
_PARAMS = "start_date=2026-01-01&end_date=2026-01-03"

_GIVEN_CHARTS = [
    {"type": "pie-chart", "name": "gender", "items": [{"name": "female", "value": 223}, {"name": "male", "value": 223}]},
    {"type": "horizontal-bar-chart", "name": "region", "items": [{"name": "Lusaka", "value": 223}]},
]


def _encode_institution_id(name: str) -> str:
    return base64.urlsafe_b64encode(name.encode()).decode().rstrip("=")


@pytest.fixture(scope="function")
def client_with_mocks() -> Generator[TestClientWithMocks, None, None]:
    mocked_repository = AsyncMock(spec=DemographicsRepository)

    app = FastAPI()
    app.dependency_overrides[get_demographics_repository] = lambda: mocked_repository

    router = APIRouter(prefix="/analytics", tags=["analytics"])
    add_demographics_routes(router)
    app.include_router(router)

    yield TestClient(app, raise_server_exceptions=False), mocked_repository


class TestGetDemographics:
    def test_returns_200_with_charts_when_api_key_present(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_demographics = AsyncMock(return_value=_GIVEN_CHARTS)

        actual_response = client.get(f"/analytics/demographics?{_PARAMS}", headers=_API_KEY_HEADER)

        assert actual_response.status_code == HTTPStatus.OK
        assert actual_response.json() == _GIVEN_CHARTS
        assert mocked_repository.get_demographics.call_args.kwargs["institution_names"] is None

    def test_returns_403_when_no_api_key(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_demographics = AsyncMock()

        actual_response = client.get(f"/analytics/demographics?{_PARAMS}")

        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        mocked_repository.get_demographics.assert_not_called()

    def test_scopes_to_multiple_institutions_when_param_given(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_demographics = AsyncMock(return_value=_GIVEN_CHARTS)
        institution_ids = ",".join([_encode_institution_id("Test School"), _encode_institution_id("Other School")])

        actual_response = client.get(
            f"/analytics/demographics?{_PARAMS}&institution_ids={institution_ids}", headers=_API_KEY_HEADER
        )

        assert actual_response.status_code == HTTPStatus.OK
        assert mocked_repository.get_demographics.call_args.kwargs["institution_names"] == [
            "Test School",
            "Other School",
        ]

    def test_returns_500_when_repository_raises(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_demographics = AsyncMock(side_effect=Exception("db down"))

        actual_response = client.get(f"/analytics/demographics?{_PARAMS}", headers=_API_KEY_HEADER)

        assert actual_response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_returns_400_when_start_after_end(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_demographics = AsyncMock()

        actual_response = client.get(
            "/analytics/demographics?start_date=2026-02-01&end_date=2026-01-01",
            headers=_API_KEY_HEADER,
        )

        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        mocked_repository.get_demographics.assert_not_called()

    def test_returns_400_for_invalid_granularity(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_demographics = AsyncMock()

        actual_response = client.get(f"/analytics/demographics?{_PARAMS}&granularity=year", headers=_API_KEY_HEADER)

        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        mocked_repository.get_demographics.assert_not_called()

    def test_returns_422_when_required_date_params_are_missing(self, client_with_mocks: TestClientWithMocks):
        client, mocked_repository = client_with_mocks
        mocked_repository.get_demographics = AsyncMock()

        actual_response = client.get("/analytics/demographics", headers=_API_KEY_HEADER)

        assert actual_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        mocked_repository.get_demographics.assert_not_called()
