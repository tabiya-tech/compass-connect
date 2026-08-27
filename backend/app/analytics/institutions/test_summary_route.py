"""
Tests for GET /analytics/institutions/summary — the server-to-server endpoint
consumed by compass-analytics. Protected by ApiKeyAuth (x-api-key header presence).
"""
import base64
from http import HTTPStatus
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, FastAPI
from starlette.testclient import TestClient

from app.analytics.institutions.repository import InstitutionRepository, get_institution_repository
from app.analytics.institutions.routes import add_institutions_routes
from app.analytics.types import Institution
from app.users.auth import Authentication

_API_KEY_HEADER = {"x-api-key": "some-key"}


def _encode_id(name: str) -> str:
    return base64.urlsafe_b64encode(name.encode()).decode().rstrip("=")


_GIVEN_INSTITUTIONS = [
    Institution(
        id=_encode_id("Lusaka College"),
        name="Lusaka College",
        active=True,
        students=1200,
        active_7_days=340,
        skills_discovery_started_pct=72.5,
        skills_discovery_completed_pct=48.0,
        career_readiness_started_pct=60.0,
        career_readiness_completed_pct=35.0,
        career_explorer_started_pct=40.0,
    ),
    Institution(
        id=_encode_id("Ndola Institute"),
        name="Ndola Institute",
        active=True,
        students=800,
        active_7_days=210,
        skills_discovery_started_pct=None,
        skills_discovery_completed_pct=None,
        career_readiness_started_pct=None,
        career_readiness_completed_pct=None,
        career_explorer_started_pct=None,
    ),
]


@pytest.fixture()
def client_with_mocks():
    mocked_repository = AsyncMock(spec=InstitutionRepository)
    mocked_repository.list_institutions = AsyncMock(return_value=(_GIVEN_INSTITUTIONS, None, False))

    app = FastAPI()
    # add_institutions_routes requires an Authentication instance for the user-facing routes.
    app.dependency_overrides[get_institution_repository] = lambda: mocked_repository

    router = APIRouter(prefix="/analytics", tags=["analytics"])
    add_institutions_routes(router, Authentication())
    app.include_router(router)

    return TestClient(app, raise_server_exceptions=False), mocked_repository


class TestGetInstitutionsSummary:
    def test_returns_200_with_all_institutions_when_api_key_present(self, client_with_mocks):
        client, _ = client_with_mocks

        # WHEN the endpoint is called with a valid x-api-key header
        actual_response = client.get("/analytics/institutions/summary", headers=_API_KEY_HEADER)

        # THEN the response is OK and contains all institutions
        assert actual_response.status_code == HTTPStatus.OK
        body = actual_response.json()
        assert len(body["institutions"]) == 2
        assert body["institutions"][0]["institution_name"] == "Lusaka College"
        assert body["institutions"][0]["registered_users"] == 1200
        assert body["institutions"][0]["active_users_7d"] == 340
        assert body["institutions"][0]["skills_discovery_started_pct"] == 72.5

    def test_returns_403_when_no_api_key(self, client_with_mocks):
        client, mocked_repository = client_with_mocks

        # WHEN the endpoint is called without the x-api-key header
        actual_response = client.get("/analytics/institutions/summary")

        # THEN access is rejected and the repository is not called
        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        mocked_repository.list_institutions.assert_not_called()

    def test_passes_decoded_names_to_repository_when_institution_ids_given(self, client_with_mocks):
        client, mocked_repository = client_with_mocks
        lusaka_id = _encode_id("Lusaka College")

        # WHEN institution_ids is scoped to one institution
        actual_response = client.get(
            f"/analytics/institutions/summary?institution_ids={lusaka_id}", headers=_API_KEY_HEADER
        )

        # THEN the repository is called with the decoded names set
        assert actual_response.status_code == HTTPStatus.OK
        mocked_repository.list_institutions.assert_called_once_with(names={"Lusaka College"})

    def test_passes_none_names_to_repository_when_no_institution_ids_given(self, client_with_mocks):
        client, mocked_repository = client_with_mocks

        # WHEN no institution_ids filter is provided
        actual_response = client.get("/analytics/institutions/summary", headers=_API_KEY_HEADER)

        # THEN the repository is called with names=None (fetch all)
        assert actual_response.status_code == HTTPStatus.OK
        mocked_repository.list_institutions.assert_called_once_with(names=None)

    def test_returns_empty_list_when_institution_id_matches_nothing(self, client_with_mocks):
        client, mocked_repository = client_with_mocks
        unknown_id = _encode_id("Unknown School")
        mocked_repository.list_institutions = AsyncMock(return_value=([], None, False))

        # WHEN institution_ids references an institution not in the DB
        actual_response = client.get(
            f"/analytics/institutions/summary?institution_ids={unknown_id}", headers=_API_KEY_HEADER
        )

        # THEN an empty institutions list is returned
        assert actual_response.status_code == HTTPStatus.OK
        assert actual_response.json()["institutions"] == []

    def test_includes_all_required_fields_in_each_institution(self, client_with_mocks):
        client, _ = client_with_mocks

        # WHEN the endpoint is called
        institutions = client.get(
            "/analytics/institutions/summary", headers=_API_KEY_HEADER
        ).json()["institutions"]

        # THEN each institution has the required fields
        for inst in institutions:
            assert "institution_id" in inst
            assert "institution_name" in inst
            assert "registered_users" in inst
            assert "active_users_7d" in inst
