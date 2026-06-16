from http import HTTPStatus
from typing import Optional
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.matching.client import MatchingServiceError
from app.matching.matching_types import (
    CompassMatchingResult,
    CompassOpportunity,
)
from app.analytics.types import PaginatedListMeta, PaginatedListResponse
from app.job_preferences.get_job_preferences_service import get_job_preferences_service
from app.job_preferences.service import IJobPreferencesService
from app.jobs import routes as jobs_routes_module
from app.jobs.get_job_service import get_job_service
from app.jobs.routes import add_jobs_routes
from app.jobs.service import IJobService, JobDocument, JobStats
from app.programme_skills.repository import ProgrammeSkillsRepository
from app.user_profile.repository import UserProfileRepository
from common_libs.test_utilities.mock_auth import MockAuth


class _MockJobService(IJobService):
    async def get_job_stats(self) -> JobStats:
        return JobStats(total=0, sectors=0, platforms=0)

    async def list_jobs(
        self,
        search: Optional[str],
        category: Optional[str],
        employment_type: Optional[str],
        location: Optional[str],
        skills: Optional[str],
        days: Optional[int],
        cursor: Optional[str],
        limit: int,
        include: Optional[str],
    ) -> PaginatedListResponse[JobDocument]:
        return PaginatedListResponse(
            data=[{"title": "Engineer"}],
            meta=PaginatedListMeta(limit=limit, next_cursor=None, has_more=False, total=None),
        )


@pytest.fixture(scope="function")
def client_with_mock_service() -> tuple[TestClient, _MockJobService]:
    service = _MockJobService()

    def _override_get_job_service() -> IJobService:
        return service

    app = FastAPI()
    app.dependency_overrides[get_job_service] = _override_get_job_service
    add_jobs_routes(app)
    client = TestClient(app)
    return client, service


class TestJobsRoutes:
    def test_get_jobs_returns_paginated_response(self, client_with_mock_service: tuple[TestClient, _MockJobService]):
        # GIVEN route registered with mocked service
        client, _ = client_with_mock_service

        # WHEN GET /jobs is called
        response = client.get("/jobs")

        # THEN response is 200 and returns data/meta shape
        assert response.status_code == HTTPStatus.OK
        body = response.json()
        assert body["data"][0]["title"] == "Engineer"
        assert body["meta"]["limit"] == 20
        assert body["meta"]["has_more"] is False

    def test_get_jobs_maps_matching_service_error_to_500(self, client_with_mock_service: tuple[TestClient, _MockJobService], monkeypatch):
        # GIVEN the service raises MatchingServiceError (the upstream is unavailable)
        client, service = client_with_mock_service

        async def _raise_matching_error(*_args, **_kwargs):
            raise MatchingServiceError("upstream down")

        monkeypatch.setattr(service, "list_jobs", _raise_matching_error)

        # WHEN GET /jobs is called
        response = client.get("/jobs")

        # THEN route maps it to 500 with the unavailable detail
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert response.json()["detail"] == "Matching service unavailable"

    def test_get_jobs_preserves_http_exception(self, client_with_mock_service: tuple[TestClient, _MockJobService], monkeypatch):
        # GIVEN service raises HTTPException
        client, service = client_with_mock_service

        async def _raise_http_exception(*_args, **_kwargs):
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid cursor")

        monkeypatch.setattr(service, "list_jobs", _raise_http_exception)

        # WHEN GET /jobs is called
        response = client.get("/jobs?cursor=bad")

        # THEN HTTPException is propagated as-is
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json()["detail"] == "Invalid cursor"

    def test_get_jobs_forwards_filters_and_cursor_to_service(self, client_with_mock_service: tuple[TestClient, _MockJobService], monkeypatch):
        # GIVEN a service that captures the forwarded arguments
        client, service = client_with_mock_service
        captured: dict = {}

        async def _capture(*_args, **kwargs):
            captured.update(kwargs)
            return PaginatedListResponse(
                data=[],
                meta=PaginatedListMeta(limit=kwargs["limit"], next_cursor="nxt", has_more=True, total=5),
            )

        monkeypatch.setattr(service, "list_jobs", _capture)

        # WHEN GET /jobs is called with filters, a cursor and include=count
        response = client.get("/jobs?skills=welding&category=Eng&cursor=abc&include=count")

        # THEN the query params are forwarded verbatim to the service
        assert response.status_code == HTTPStatus.OK
        assert captured["skills"] == "welding"
        assert captured["category"] == "Eng"
        assert captured["cursor"] == "abc"
        assert captured["include"] == "count"
        assert response.json()["meta"]["next_cursor"] == "nxt"


_MatchedFixtureMocks = dict


@pytest.fixture(scope="function")
def matched_client(monkeypatch) -> tuple[TestClient, _MatchedFixtureMocks]:
    """Build a TestClient with the /jobs/matched route registered and all dependencies mocked."""
    # Mock the user profile repository (returns a programme + province)
    mock_user_profile_repo = AsyncMock(spec=UserProfileRepository)
    mock_user_profile_repo.get_latest_session_id.return_value = 42
    mock_user_profile_repo.get_personal_data.return_value = {
        "province": "Lusaka",
        "programme_name": "Software Engineering",
    }

    # Mock the programme skills repository (no skills by default)
    mock_programme_skills_repo = AsyncMock(spec=ProgrammeSkillsRepository)
    mock_programme_skills_repo.find_by_programme_name.return_value = None

    # Mock the job preferences service (no prefs by default)
    mock_prefs_service = AsyncMock(spec=IJobPreferencesService)
    mock_prefs_service.get_by_session.return_value = None

    # Mock the job service (the matched route no longer uses it, but it is still
    # registered as an app dependency by add_jobs_routes).
    mock_job_service = AsyncMock(spec=IJobService)

    # Mock the matching service (returns an empty CompassMatchingResult by default).
    # Despite the variable name (kept stable for existing assertions), this is a
    # MatchingService wrapper that yields CompassMatchingResult, not the raw HTTP client.
    mock_matching_client = AsyncMock()
    mock_matching_client.generate_recommendations.return_value = CompassMatchingResult(
        user_id="mock-user",
        algorithm_version="v1",
    )

    # Patch the get_matching_service symbol imported into the routes module (handler calls it directly, not via Depends)
    monkeypatch.setattr(jobs_routes_module, "get_matching_service", lambda: mock_matching_client)

    # Override the Depends() factories
    async def _override_user_profile_repo():
        return mock_user_profile_repo

    async def _override_programme_skills_repo():
        return mock_programme_skills_repo

    def _override_get_prefs_service() -> IJobPreferencesService:
        return mock_prefs_service

    def _override_get_job_service() -> IJobService:
        return mock_job_service

    auth = MockAuth()
    app = FastAPI()
    app.dependency_overrides[jobs_routes_module._get_user_profile_repository] = _override_user_profile_repo
    app.dependency_overrides[jobs_routes_module._get_programme_skills_repository] = _override_programme_skills_repo
    app.dependency_overrides[get_job_preferences_service] = _override_get_prefs_service
    app.dependency_overrides[get_job_service] = _override_get_job_service

    add_jobs_routes(app, auth)
    client = TestClient(app)

    yield client, {
        "user_profile_repo": mock_user_profile_repo,
        "programme_skills_repo": mock_programme_skills_repo,
        "prefs_service": mock_prefs_service,
        "job_service": mock_job_service,
        "matching_client": mock_matching_client,
        "auth_user": auth.mocked_user,
    }

    app.dependency_overrides = {}


def _given_programme_skills_doc():
    """Return a stub programme_skills doc with one skill — enough to populate skills_vector."""
    skill = type("Skill", (), {
        "UUID": "skill-uuid-1",
        "originUUID": "skill-origin-1",
        "preferredLabel": "Python programming",
        "skillType": "skill/competence",
    })()
    return type("ProgrammeSkillsDoc", (), {"skills": [skill]})()


class TestMatchedJobsRoute:
    def test_calls_matching_service_with_authenticated_user_context_when_programme_skills_exist(
        self, matched_client: tuple[TestClient, _MatchedFixtureMocks]
    ):
        # GIVEN the user has a programme on file with at least one programme-catalog skill
        client, mocks = matched_client
        mocks["user_profile_repo"].get_explored_experience_entities.return_value = None
        mocks["programme_skills_repo"].find_by_programme_name.return_value = _given_programme_skills_doc()

        # WHEN GET /jobs/matched is called
        actual_response = client.get("/jobs/matched")

        # THEN the matching service is called with the authenticated user's id, province, and programme skills
        assert actual_response.status_code == HTTPStatus.OK
        assert mocks["matching_client"].generate_recommendations.await_count == 1
        actual_call_kwargs = mocks["matching_client"].generate_recommendations.call_args.kwargs
        assert actual_call_kwargs["youth_id"] == mocks["auth_user"].user_id
        assert actual_call_kwargs["province"] == "Lusaka"
        assert len(actual_call_kwargs["skills_vector"].top_skills) == 1
        assert actual_response.json()["skills_source"] == "programme"

    def test_surfaces_matching_service_fields_on_matches(self, matched_client: tuple[TestClient, _MatchedFixtureMocks]):
        # GIVEN the user has a programme + matching service returns one opportunity with employer/location
        client, mocks = matched_client
        mocks["user_profile_repo"].get_explored_experience_entities.return_value = None
        mocks["programme_skills_repo"].find_by_programme_name.return_value = _given_programme_skills_doc()
        given_url = "https://example.com/jobs/engineer-1"
        mocks["matching_client"].generate_recommendations.return_value = CompassMatchingResult(
            user_id="mock-user",
            algorithm_version="v1",
            opportunities=[
                CompassOpportunity(
                    uuid="matching-svc-id-1",
                    rank=1,
                    opportunity_title="Engineer",
                    url=given_url,
                    employer="Acme Corp",
                    location="Lusaka",
                    contract_type="full_time",
                    final_score=0.9,
                )
            ],
        )

        # WHEN GET /jobs/matched is called
        actual_response = client.get("/jobs/matched")

        # THEN the response surfaces the matching-service fields straight through (no local-DB join)
        assert actual_response.status_code == HTTPStatus.OK
        actual_body = actual_response.json()
        assert len(actual_body["matches"]) == 1
        match = actual_body["matches"][0]
        assert match["opportunity_title"] == "Engineer"
        assert match["employer"] == "Acme Corp"
        assert match["location"] == "Lusaka"
        assert match["contract_type"] == "full_time"
        assert match["URL"] == given_url
        # category/posted_date are not provided by the matching recommendation → null
        assert match["category"] is None
        assert match["posted_date"] is None

    def test_returns_500_on_matching_service_error(self, matched_client: tuple[TestClient, _MatchedFixtureMocks]):
        # GIVEN the user has a programme + matching service raises MatchingServiceError
        client, mocks = matched_client
        mocks["user_profile_repo"].get_explored_experience_entities.return_value = None
        mocks["programme_skills_repo"].find_by_programme_name.return_value = _given_programme_skills_doc()
        mocks["matching_client"].generate_recommendations.side_effect = MatchingServiceError("upstream down")

        # WHEN GET /jobs/matched is called
        actual_response = client.get("/jobs/matched")

        # THEN response is 500 with the matching-service-unavailable detail
        assert actual_response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert actual_response.json()["detail"] == "Matching service unavailable"

    def test_uses_si_skills_when_explored_experiences_exist(self, matched_client: tuple[TestClient, _MatchedFixtureMocks]):
        """The S&I path takes precedence over programme catalog skills (and proves envelope shape)."""
        # GIVEN the user has explored experiences with skills (S&I done)
        client, mocks = matched_client
        from app.agent.experience.experience_entity import ExperienceEntity
        from app.vector_search.esco_entities import SkillEntity

        given_skill = SkillEntity(
            id="skill-id-1",
            UUID="si-skill-uuid-1",
            modelId="model-1",
            preferredLabel="comply with food safety and hygiene",
            altLabels=[],
            description="",
            skillType="skill/competence",
            score=0.91,
        )
        given_experience = ExperienceEntity(
            experience_title="cook",
            top_skills=[given_skill],
        )
        mocks["user_profile_repo"].get_explored_experience_entities.return_value = [given_experience]
        # AND a programme is also on file (we want to prove S&I wins)
        mocks["programme_skills_repo"].find_by_programme_name.return_value = _given_programme_skills_doc()
        # AND the matching service returns one match
        mocks["matching_client"].generate_recommendations.return_value = CompassMatchingResult(
            user_id="mock-user",
            algorithm_version="v1",
            opportunities=[
                CompassOpportunity(
                    uuid="id-1",
                    rank=1,
                    opportunity_title="Cook",
                    url="https://example.com/jobs/cook",
                    final_score=0.85,
                )
            ],
        )

        # WHEN GET /jobs/matched is called
        actual_response = client.get("/jobs/matched")

        # THEN the matching service is called with non-empty skills_vector built from the S&I experience,
        # the programme repo is NOT consulted, and the envelope reports skills_source=s&i
        assert actual_response.status_code == HTTPStatus.OK
        actual_body = actual_response.json()
        assert actual_body["skills_source"] == "s&i"
        assert len(actual_body["matches"]) == 1
        actual_call_kwargs = mocks["matching_client"].generate_recommendations.call_args.kwargs
        assert len(actual_call_kwargs["skills_vector"].top_skills) >= 1
        mocks["programme_skills_repo"].find_by_programme_name.assert_not_awaited()

    def test_short_circuits_to_empty_when_no_skills_anywhere(self, matched_client: tuple[TestClient, _MatchedFixtureMocks]):
        """The load-bearing UX guarantee: blank > random fallback. Matching service must not be called."""
        # GIVEN the user has no S&I skills AND no programme on file
        client, mocks = matched_client
        mocks["user_profile_repo"].get_explored_experience_entities.return_value = None
        mocks["user_profile_repo"].get_personal_data.return_value = None
        mocks["programme_skills_repo"].find_by_programme_name.return_value = None

        # WHEN GET /jobs/matched is called
        actual_response = client.get("/jobs/matched")

        # THEN response is the empty envelope AND the matching service was NOT called
        assert actual_response.status_code == HTTPStatus.OK
        assert actual_response.json() == {"matches": [], "skills_source": "none"}
        mocks["matching_client"].generate_recommendations.assert_not_awaited()
