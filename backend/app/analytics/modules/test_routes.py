"""
Tests for the module analytics routes: build-your-profile, job-readiness, jobs and
career-explorer.

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
    CareerExplorerModuleRepository,
    JobReadinessAnalyticsRepository,
    ModuleAnalyticsRepository,
    get_career_explorer_module_repository,
    get_module_analytics_repository,
)
from app.analytics.modules.routes import (
    add_modules_analytics_routes,
    _get_job_readiness_repository,
)
from app.analytics.modules.types import JobReadinessResponse, SubModuleProgress
from app.jobs.get_job_service import get_job_service
from app.jobs.service import IJobService, JobStats

TestClientWithMocks = tuple[TestClient, ModuleAnalyticsRepository]
TestClientWithJobReadinessMocks = tuple[TestClient, JobReadinessAnalyticsRepository]
TestClientWithJobServiceMock = tuple[TestClient, AsyncMock]
CareerExplorerClientWithMocks = tuple[TestClient, CareerExplorerModuleRepository]

_CE_PARAMS = "start_date=2026-01-01&end_date=2026-06-30"

# The shape app/analytics/career_explorer/types.py defines, which this route reuses verbatim.
_GIVEN_CAREER_EXPLORER = {
    "total_registered_students": 12_450,
    "started": {"count": 2_241, "percentage": 18.0},
    "returned_2_plus": {"count": 890, "percentage": 39.7},
    "priority_sector_users": 640,
    "non_priority_sector_users": 1_601,
    "top_sectors": [
        {"sector_name": "Healthcare", "is_priority": True, "unique_users": 188, "total_inquiries": 421},
        {"sector_name": "Technology", "is_priority": False, "unique_users": 152, "total_inquiries": 310},
    ],
}

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


@pytest.fixture(scope="function")
def career_explorer_client_with_mocks() -> Generator[CareerExplorerClientWithMocks, None, None]:
    mocked_repository = AsyncMock(spec=CareerExplorerModuleRepository)

    app = FastAPI()
    app.dependency_overrides[get_career_explorer_module_repository] = lambda: mocked_repository

    router = APIRouter(prefix="/analytics", tags=["analytics"])
    add_modules_analytics_routes(router)
    app.include_router(router)

    yield TestClient(app, raise_server_exceptions=False), mocked_repository


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


class TestGetCareerExplorer:
    def test_should_return_200_with_data_when_api_key_present(
        self, career_explorer_client_with_mocks: CareerExplorerClientWithMocks
    ):
        # GIVEN the repository returns career explorer data
        client, mocked_repository = career_explorer_client_with_mocks
        mocked_repository.get_career_explorer = AsyncMock(return_value=_GIVEN_CAREER_EXPLORER)

        # WHEN the endpoint is called with a valid x-api-key header
        actual_response = client.get(f"/analytics/modules/career-explorer?{_CE_PARAMS}", headers=_API_KEY_HEADER)

        # THEN the response is OK, carrying every figure the repository reported
        assert actual_response.status_code == HTTPStatus.OK
        actual_body = actual_response.json()
        assert actual_body["total_registered_students"] == 12_450
        assert actual_body["started"] == {"count": 2_241, "percentage": 18.0}
        assert actual_body["returned_2_plus"] == {"count": 890, "percentage": 39.7}
        assert actual_body["priority_sector_users"] == 640
        assert actual_body["non_priority_sector_users"] == 1_601
        assert actual_body["top_sectors"][0]["sector_name"] == "Healthcare"
        assert actual_body["top_sectors"][0]["is_priority"] is True

    def test_should_return_403_when_no_api_key(
        self, career_explorer_client_with_mocks: CareerExplorerClientWithMocks
    ):
        # GIVEN no x-api-key header
        client, mocked_repository = career_explorer_client_with_mocks
        mocked_repository.get_career_explorer = AsyncMock()

        # WHEN the endpoint is called without authentication
        actual_response = client.get(f"/analytics/modules/career-explorer?{_CE_PARAMS}")

        # THEN expect 403 (ApiKeyAuth yields 403 when header is absent), and no query is run
        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        mocked_repository.get_career_explorer.assert_not_called()

    def test_should_return_422_when_the_window_is_missing(
        self, career_explorer_client_with_mocks: CareerExplorerClientWithMocks
    ):
        # GIVEN no date range
        client, mocked_repository = career_explorer_client_with_mocks
        mocked_repository.get_career_explorer = AsyncMock()

        # WHEN the endpoint is called without the required params
        actual_response = client.get("/analytics/modules/career-explorer", headers=_API_KEY_HEADER)

        # THEN expect a validation error and no query
        assert actual_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        mocked_repository.get_career_explorer.assert_not_called()

    def test_should_return_400_when_start_date_is_after_end_date(
        self, career_explorer_client_with_mocks: CareerExplorerClientWithMocks
    ):
        # GIVEN a window whose start falls after its end
        client, mocked_repository = career_explorer_client_with_mocks
        mocked_repository.get_career_explorer = AsyncMock()

        # WHEN the endpoint is called
        actual_response = client.get(
            "/analytics/modules/career-explorer?start_date=2026-06-30&end_date=2026-01-01", headers=_API_KEY_HEADER
        )

        # THEN expect it rejected before any query runs
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        mocked_repository.get_career_explorer.assert_not_called()

    def test_should_return_400_for_an_unsupported_granularity(
        self, career_explorer_client_with_mocks: CareerExplorerClientWithMocks
    ):
        # GIVEN a granularity outside the shared vocabulary
        client, mocked_repository = career_explorer_client_with_mocks
        mocked_repository.get_career_explorer = AsyncMock()

        # WHEN the endpoint is called
        actual_response = client.get(
            f"/analytics/modules/career-explorer?{_CE_PARAMS}&granularity=quarter", headers=_API_KEY_HEADER
        )

        # THEN expect it rejected before any query runs
        assert actual_response.status_code == HTTPStatus.BAD_REQUEST
        mocked_repository.get_career_explorer.assert_not_called()

    def test_should_widen_the_window_to_whole_utc_days(
        self, career_explorer_client_with_mocks: CareerExplorerClientWithMocks
    ):
        # GIVEN an inclusive yyyy-MM-dd window
        client, mocked_repository = career_explorer_client_with_mocks
        mocked_repository.get_career_explorer = AsyncMock(return_value=_GIVEN_CAREER_EXPLORER)

        # WHEN the endpoint is called
        client.get(f"/analytics/modules/career-explorer?{_CE_PARAMS}", headers=_API_KEY_HEADER)

        # THEN the end date covers its whole day, so activity late on the last day still counts
        actual_kwargs = mocked_repository.get_career_explorer.call_args.kwargs
        assert actual_kwargs["start_date"].isoformat() == "2026-01-01T00:00:00+00:00"
        assert actual_kwargs["end_date"].isoformat() == "2026-06-30T23:59:59.999999+00:00"

    def test_should_pass_no_institution_names_when_institution_ids_omitted(
        self, career_explorer_client_with_mocks: CareerExplorerClientWithMocks
    ):
        # GIVEN no institution_ids param
        client, mocked_repository = career_explorer_client_with_mocks
        mocked_repository.get_career_explorer = AsyncMock(return_value=_GIVEN_CAREER_EXPLORER)

        # WHEN the endpoint is called without institution_ids
        client.get(f"/analytics/modules/career-explorer?{_CE_PARAMS}", headers=_API_KEY_HEADER)

        # THEN the repository is asked for every institution
        assert mocked_repository.get_career_explorer.call_args.kwargs["institution_names"] is None

    def test_should_decode_multiple_institution_ids(
        self, career_explorer_client_with_mocks: CareerExplorerClientWithMocks
    ):
        # GIVEN two base64url-encoded institution IDs
        client, mocked_repository = career_explorer_client_with_mocks
        mocked_repository.get_career_explorer = AsyncMock(return_value=_GIVEN_CAREER_EXPLORER)
        given_ids = f"{_encode_institution_id('Lusaka College')},{_encode_institution_id('Ndola Trust')}"

        # WHEN the endpoint is called with both
        client.get(
            f"/analytics/modules/career-explorer?{_CE_PARAMS}&institution_ids={given_ids}", headers=_API_KEY_HEADER
        )

        # THEN both decoded names scope the query
        assert mocked_repository.get_career_explorer.call_args.kwargs["institution_names"] == [
            "Lusaka College",
            "Ndola Trust",
        ]

    def test_should_return_500_when_the_repository_raises(
        self, career_explorer_client_with_mocks: CareerExplorerClientWithMocks
    ):
        # GIVEN the aggregation blows up
        client, mocked_repository = career_explorer_client_with_mocks
        mocked_repository.get_career_explorer = AsyncMock(side_effect=RuntimeError("mongo is down"))

        # WHEN the endpoint is called
        actual_response = client.get(f"/analytics/modules/career-explorer?{_CE_PARAMS}", headers=_API_KEY_HEADER)

        # THEN it answers with a clean error rather than leaking the exception
        assert actual_response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert actual_response.json()["detail"] == "Unexpected error fetching career explorer analytics"

    def test_should_not_affect_the_job_readiness_route(
        self, career_explorer_client_with_mocks: CareerExplorerClientWithMocks
    ):
        # GIVEN both module routes registered on the same router (see the fixture)
        client, _ = career_explorer_client_with_mocks

        # WHEN the pre-existing job-readiness route is called without a key
        actual_response = client.get("/analytics/modules/job-readiness")

        # THEN it still answers as it did before — adding career-explorer left it untouched
        assert actual_response.status_code == HTTPStatus.FORBIDDEN
