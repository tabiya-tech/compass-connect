"""
Tests for GET /analytics/modules/job-readiness.

Server-to-server endpoint (x-api-key auth), same pattern as /analytics/reach.
Institution scope is passed as a comma-separated list of base64url-encoded IDs.
"""
import base64
from http import HTTPStatus
from typing import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, FastAPI
from starlette.testclient import TestClient

from app.analytics.modules.repository import JobReadinessAnalyticsRepository
from app.analytics.modules.routes import add_modules_analytics_routes, _get_job_readiness_repository
from app.analytics.modules.types import JobReadinessResponse, SubModuleProgress

TestClientWithMocks = tuple[TestClient, JobReadinessAnalyticsRepository]

_API_KEY_HEADER = {"x-api-key": "some-key"}

_GIVEN_JOB_READINESS = JobReadinessResponse(
    started_percentage=34.0,
    sub_modules=[
        SubModuleProgress(id="cv-development", name="CV Development", started=1200, completed=663),
        SubModuleProgress(id="interview-preparation", name="Interview Preparation", started=1500, completed=981),
    ],
)


def _encode_institution_id(name: str) -> str:
    return base64.urlsafe_b64encode(name.encode()).decode().rstrip("=")


@pytest.fixture(scope="function")
def client_with_mocks() -> Generator[TestClientWithMocks, None, None]:
    mocked_repository = AsyncMock(spec=JobReadinessAnalyticsRepository)

    app = FastAPI()
    app.dependency_overrides[_get_job_readiness_repository] = lambda: mocked_repository

    router = APIRouter(prefix="/analytics", tags=["analytics"])
    add_modules_analytics_routes(router)
    app.include_router(router)

    yield TestClient(app, raise_server_exceptions=False), mocked_repository


class TestGetJobReadiness:
    def test_should_return_200_with_data_when_api_key_present(self, client_with_mocks: TestClientWithMocks):
        # GIVEN the repository returns job readiness data
        client, mocked_repository = client_with_mocks
        mocked_repository.get_job_readiness = AsyncMock(return_value=_GIVEN_JOB_READINESS)

        # WHEN the endpoint is called with a valid x-api-key header
        actual_response = client.get("/analytics/modules/job-readiness", headers=_API_KEY_HEADER)

        # THEN the response is OK with the expected payload
        assert actual_response.status_code == HTTPStatus.OK
        body = actual_response.json()
        assert body["started_percentage"] == 34.0
        assert len(body["sub_modules"]) == 2
        assert body["sub_modules"][0]["id"] == "cv-development"
        assert body["sub_modules"][0]["started"] == 1200
        assert body["degraded"] is False

    def test_should_return_403_when_no_api_key(self, client_with_mocks: TestClientWithMocks):
        # GIVEN no x-api-key header
        client, mocked_repository = client_with_mocks
        mocked_repository.get_job_readiness = AsyncMock()

        # WHEN the endpoint is called without authentication
        actual_response = client.get("/analytics/modules/job-readiness")

        # THEN expect 403 (ApiKeyAuth yields 403 when header is absent)
        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        mocked_repository.get_job_readiness.assert_not_called()

    def test_should_pass_no_institution_names_when_institution_ids_omitted(
        self, client_with_mocks: TestClientWithMocks
    ):
        # GIVEN no institution_ids param
        client, mocked_repository = client_with_mocks
        mocked_repository.get_job_readiness = AsyncMock(return_value=_GIVEN_JOB_READINESS)

        # WHEN the endpoint is called without institution_ids
        client.get("/analytics/modules/job-readiness", headers=_API_KEY_HEADER)

        # THEN the repository is called with None (all institutions)
        mocked_repository.get_job_readiness.assert_called_once_with(None)

    def test_should_decode_and_pass_institution_names_when_institution_ids_given(
        self, client_with_mocks: TestClientWithMocks
    ):
        # GIVEN a single base64url-encoded institution ID
        client, mocked_repository = client_with_mocks
        mocked_repository.get_job_readiness = AsyncMock(return_value=_GIVEN_JOB_READINESS)
        encoded = _encode_institution_id("Lusaka College")

        # WHEN the endpoint is called with that institution_id
        client.get(f"/analytics/modules/job-readiness?institution_ids={encoded}", headers=_API_KEY_HEADER)

        # THEN the repository is called with the decoded institution name
        mocked_repository.get_job_readiness.assert_called_once_with(["Lusaka College"])

    def test_should_decode_multiple_institution_ids(self, client_with_mocks: TestClientWithMocks):
        # GIVEN two base64url-encoded institution IDs
        client, mocked_repository = client_with_mocks
        mocked_repository.get_job_readiness = AsyncMock(return_value=_GIVEN_JOB_READINESS)
        encoded_a = _encode_institution_id("Lusaka College")
        encoded_b = _encode_institution_id("Ndola Institute")

        # WHEN the endpoint is called with both institution_ids
        client.get(
            f"/analytics/modules/job-readiness?institution_ids={encoded_a},{encoded_b}",
            headers=_API_KEY_HEADER,
        )

        # THEN the repository is called with both decoded institution names
        call_arg = mocked_repository.get_job_readiness.call_args[0][0]
        assert "Lusaka College" in call_arg
        assert "Ndola Institute" in call_arg

    def test_should_skip_malformed_institution_ids_gracefully(self, client_with_mocks: TestClientWithMocks):
        # GIVEN one valid and one malformed (not base64) institution ID
        client, mocked_repository = client_with_mocks
        mocked_repository.get_job_readiness = AsyncMock(return_value=_GIVEN_JOB_READINESS)
        encoded = _encode_institution_id("Lusaka College")

        # WHEN the endpoint is called
        actual_response = client.get(
            f"/analytics/modules/job-readiness?institution_ids={encoded},!!!not-base64!!!",
            headers=_API_KEY_HEADER,
        )

        # THEN the endpoint still returns 200 (malformed IDs are skipped, not rejected)
        assert actual_response.status_code == HTTPStatus.OK
        call_arg = mocked_repository.get_job_readiness.call_args[0][0]
        assert "Lusaka College" in call_arg
