"""
Tests for the module analytics routes: build-your-profile, job-readiness, and jobs.

Server-to-server endpoints (x-api-key auth), same pattern as /analytics/reach.
Institution scope is passed as a comma-separated list of base64url-encoded IDs.
"""
import base64
from http import HTTPStatus
from typing import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, FastAPI
from starlette.testclient import TestClient

from app.analytics.modules.repository import (
    JobReadinessAnalyticsRepository,
    ModuleAnalyticsRepository,
    get_module_analytics_repository,
)
from app.analytics.modules.routes import add_modules_analytics_routes, _get_job_readiness_repository
from app.analytics.modules.types import JobReadinessResponse, SubModuleProgress
from app.jobs.get_job_service import get_job_service
from app.jobs.service import IJobService, JobStats

TestClientWithMocks = tuple[TestClient, ModuleAnalyticsRepository]
TestClientWithJobReadinessMocks = tuple[TestClient, JobReadinessAnalyticsRepository]
TestClientWithJobServiceMock = tuple[TestClient, AsyncMock]

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
    mocked_repository = AsyncMock(spec=ModuleAnalyticsRepository)

    app = FastAPI()
    app.dependency_overrides[get_module_analytics_repository] = lambda: mocked_repository

    router = APIRouter(prefix="/analytics", tags=["analytics"])
    add_modules_analytics_routes(router)
    app.include_router(router)

    yield TestClient(app, raise_server_exceptions=False), mocked_repository


@pytest.fixture(scope="function")
def client_with_job_readiness_mocks() -> Generator[TestClientWithJobReadinessMocks, None, None]:
    mocked_repository = AsyncMock(spec=JobReadinessAnalyticsRepository)

    app = FastAPI()
    app.dependency_overrides[_get_job_readiness_repository] = lambda: mocked_repository

    router = APIRouter(prefix="/analytics", tags=["analytics"])
    add_modules_analytics_routes(router)
    app.include_router(router)

    yield TestClient(app, raise_server_exceptions=False), mocked_repository


@pytest.fixture(scope="function")
def client_with_job_service_mock() -> Generator[TestClientWithJobServiceMock, None, None]:
    mocked_job_service = AsyncMock(spec=IJobService)

    app = FastAPI()
    app.dependency_overrides[get_job_service] = lambda: mocked_job_service

    router = APIRouter(prefix="/analytics", tags=["analytics"])
    add_modules_analytics_routes(router)
    app.include_router(router)

    yield TestClient(app, raise_server_exceptions=False), mocked_job_service


class TestGetBuildYourProfile:
    def test_returns_200_with_composed_summary_and_series_when_api_key_present(
        self, client_with_mocks: TestClientWithMocks
    ):
        # GIVEN the repository returns build-your-profile data
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock(return_value=_GIVEN_BYP)

        # WHEN the endpoint is called with a valid x-api-key header
        actual_response = client.get(f"/analytics/modules/build-your-profile?{_PARAMS}", headers=_API_KEY_HEADER)

        # THEN the response is OK with the composed summary, series, and phases
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
        # GIVEN no x-api-key header
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock()

        # WHEN the endpoint is called without authentication
        actual_response = client.get(f"/analytics/modules/build-your-profile?{_PARAMS}")

        # THEN expect 403 (ApiKeyAuth yields 403 when header is absent)
        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        mocked_repository.get_build_your_profile.assert_not_called()

    def test_scopes_to_multiple_institutions_when_param_given(self, client_with_mocks: TestClientWithMocks):
        # GIVEN two base64url-encoded institution IDs
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock(return_value=_GIVEN_BYP)
        institution_ids = ",".join([_encode_institution_id("Test School"), _encode_institution_id("Other School")])

        # WHEN the endpoint is called with both institution_ids
        actual_response = client.get(
            f"/analytics/modules/build-your-profile?{_PARAMS}&institution_ids={institution_ids}",
            headers=_API_KEY_HEADER,
        )

        # THEN the repository is called with both decoded institution names
        assert actual_response.status_code == HTTPStatus.OK
        assert mocked_repository.get_build_your_profile.call_args.kwargs["institution_names"] == [
            "Test School",
            "Other School",
        ]

    def test_forwards_granularity_to_the_repository(self, client_with_mocks: TestClientWithMocks):
        # GIVEN a granularity of "week"
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock(return_value=_GIVEN_BYP)

        # WHEN the endpoint is called with that granularity
        actual_response = client.get(
            f"/analytics/modules/build-your-profile?{_PARAMS}&granularity=week", headers=_API_KEY_HEADER
        )

        # THEN the repository is called with the same granularity
        assert actual_response.status_code == HTTPStatus.OK
        assert mocked_repository.get_build_your_profile.call_args.kwargs["granularity"] == "week"

    def test_returns_400_when_start_after_end(self, client_with_mocks: TestClientWithMocks):
        # GIVEN a date range whose start falls after its end
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock()

        # WHEN the endpoint is called
        actual_response = client.get(
            "/analytics/modules/build-your-profile?start_date=2026-02-01&end_date=2026-01-01",
            headers=_API_KEY_HEADER,
        )

        # THEN expect a bad request and no call to the repository
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        mocked_repository.get_build_your_profile.assert_not_called()

    def test_returns_400_for_invalid_granularity(self, client_with_mocks: TestClientWithMocks):
        # GIVEN an unsupported granularity value
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock()

        # WHEN the endpoint is called with that value
        actual_response = client.get(
            f"/analytics/modules/build-your-profile?{_PARAMS}&granularity=year", headers=_API_KEY_HEADER
        )

        # THEN expect a bad request and no call to the repository
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        mocked_repository.get_build_your_profile.assert_not_called()

    def test_returns_500_when_repository_raises(self, client_with_mocks: TestClientWithMocks):
        # GIVEN the repository raises an unexpected error
        client, mocked_repository = client_with_mocks
        mocked_repository.get_build_your_profile = AsyncMock(side_effect=Exception("db down"))

        # WHEN the endpoint is called
        actual_response = client.get(f"/analytics/modules/build-your-profile?{_PARAMS}", headers=_API_KEY_HEADER)

        # THEN expect an internal server error
        assert actual_response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


class TestGetJobReadiness:
    def test_should_return_200_with_data_when_api_key_present(self, client_with_job_readiness_mocks: TestClientWithJobReadinessMocks):
        # GIVEN the repository returns job readiness data
        client, mocked_repository = client_with_job_readiness_mocks
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

    def test_should_return_403_when_no_api_key(self, client_with_job_readiness_mocks: TestClientWithJobReadinessMocks):
        # GIVEN no x-api-key header
        client, mocked_repository = client_with_job_readiness_mocks
        mocked_repository.get_job_readiness = AsyncMock()

        # WHEN the endpoint is called without authentication
        actual_response = client.get("/analytics/modules/job-readiness")

        # THEN expect 403 (ApiKeyAuth yields 403 when header is absent)
        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        mocked_repository.get_job_readiness.assert_not_called()

    def test_should_pass_no_institution_names_when_institution_ids_omitted(
        self, client_with_job_readiness_mocks: TestClientWithJobReadinessMocks
    ):
        # GIVEN no institution_ids param
        client, mocked_repository = client_with_job_readiness_mocks
        mocked_repository.get_job_readiness = AsyncMock(return_value=_GIVEN_JOB_READINESS)

        # WHEN the endpoint is called without institution_ids
        client.get("/analytics/modules/job-readiness", headers=_API_KEY_HEADER)

        # THEN the repository is called with None (all institutions)
        mocked_repository.get_job_readiness.assert_called_once_with(None)

    def test_should_decode_and_pass_institution_names_when_institution_ids_given(
        self, client_with_job_readiness_mocks: TestClientWithJobReadinessMocks
    ):
        # GIVEN a single base64url-encoded institution ID
        client, mocked_repository = client_with_job_readiness_mocks
        mocked_repository.get_job_readiness = AsyncMock(return_value=_GIVEN_JOB_READINESS)
        encoded = _encode_institution_id("Lusaka College")

        # WHEN the endpoint is called with that institution_id
        client.get(f"/analytics/modules/job-readiness?institution_ids={encoded}", headers=_API_KEY_HEADER)

        # THEN the repository is called with the decoded institution name
        mocked_repository.get_job_readiness.assert_called_once_with(["Lusaka College"])

    def test_should_decode_multiple_institution_ids(self, client_with_job_readiness_mocks: TestClientWithJobReadinessMocks):
        # GIVEN two base64url-encoded institution IDs
        client, mocked_repository = client_with_job_readiness_mocks
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

    def test_should_skip_malformed_institution_ids_gracefully(self, client_with_job_readiness_mocks: TestClientWithJobReadinessMocks):
        # GIVEN one valid and one malformed (not base64) institution ID
        client, mocked_repository = client_with_job_readiness_mocks
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


class TestGetJobsModule:
    def test_returns_200_with_jobs_sourced_from_the_job_service(self, client_with_job_service_mock: TestClientWithJobServiceMock):
        # GIVEN the job service returns aggregate job stats
        client, mocked_job_service = client_with_job_service_mock
        mocked_job_service.get_job_stats = AsyncMock(return_value=JobStats(total=12_345, sectors=8, platforms=3))

        # WHEN the endpoint is called with a valid x-api-key header
        actual_response = client.get("/analytics/modules/jobs", headers=_API_KEY_HEADER)

        # THEN the response is OK with jobs_sourced taken from the job service's total
        assert actual_response.status_code == HTTPStatus.OK
        assert actual_response.json() == {"summary": {"jobs_sourced": 12_345}}
        mocked_job_service.get_job_stats.assert_awaited_once_with()

    def test_returns_403_when_no_api_key(self, client_with_job_service_mock: TestClientWithJobServiceMock):
        # GIVEN no x-api-key header
        client, mocked_job_service = client_with_job_service_mock
        mocked_job_service.get_job_stats = AsyncMock()

        # WHEN the endpoint is called without authentication
        actual_response = client.get("/analytics/modules/jobs")

        # THEN expect 403 (ApiKeyAuth yields 403 when header is absent)
        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        mocked_job_service.get_job_stats.assert_not_called()

    def test_returns_500_when_job_service_raises(self, client_with_job_service_mock: TestClientWithJobServiceMock):
        # GIVEN the job service raises an unexpected error
        client, mocked_job_service = client_with_job_service_mock
        mocked_job_service.get_job_stats = AsyncMock(side_effect=Exception("matching service down"))

        # WHEN the endpoint is called
        actual_response = client.get("/analytics/modules/jobs", headers=_API_KEY_HEADER)

        # THEN expect an internal server error
        assert actual_response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
