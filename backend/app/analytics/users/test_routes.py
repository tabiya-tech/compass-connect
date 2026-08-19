"""
Tests for the /students routes.

/students is authenticated with an admin / institution-staff JWT, while /students/analytics is a
server-to-server endpoint for external providers: it is authenticated with an x-api-key header
and the caller passes the scope explicitly via the `institution` query param.
"""
import base64
from http import HTTPStatus
from typing import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.analytics.types import User
from app.analytics.users.repository import UserRepository, get_user_repository
from app.analytics.users.routes import add_users_routes
from app.users.auth import ApiKeyAuth, SignInProvider, UserInfo
from common_libs.test_utilities.mock_auth import MockAuth

TestClientWithMocks = tuple[TestClient, UserRepository]

_API_KEY_HEADER = {"x-api-key": "some-key"}
_JWT_HEADER = {"Authorization": "Bearer some-token"}

_GIVEN_USERS = [User(id="user-1", institution="Test School")]


def _encode_institution_id(name: str) -> str:
    return base64.urlsafe_b64encode(name.encode()).decode().rstrip("=")


def _build_client(user_info: UserInfo) -> TestClientWithMocks:
    mocked_repository = AsyncMock(spec=UserRepository)
    mocked_repository.list_users = AsyncMock(return_value=(_GIVEN_USERS, None, False))
    mocked_repository.count_users = AsyncMock(return_value=1)

    app = FastAPI()
    app.dependency_overrides[get_user_repository] = lambda: mocked_repository

    router = APIRouter(prefix="/students", tags=["analytics", "users"])
    add_users_routes(router, MockAuth(user_info), ApiKeyAuth())
    app.include_router(router)

    return TestClient(app, raise_server_exceptions=False), mocked_repository


def _user_info(role: str | None, institution_id: str | None = None) -> UserInfo:
    return UserInfo(
        user_id="user-id",
        token="token", # nosec B106
        sign_in_provider=SignInProvider.PASSWORD,
        role=role,
        institution_id=institution_id,
    )


@pytest.fixture(scope="function")
def admin_client() -> Generator[TestClientWithMocks, None, None]:
    yield _build_client(_user_info(role="admin"))


@pytest.fixture(scope="function")
def institution_staff_client() -> Generator[TestClientWithMocks, None, None]:
    yield _build_client(_user_info(role="institution_staff", institution_id=_encode_institution_id("Staff School")))


class TestListStudents:
    def test_returns_200_when_admin_jwt_is_given(self, admin_client: TestClientWithMocks):
        # GIVEN an admin JWT caller
        client, mocked_repository = admin_client

        # WHEN /students is called with the Authorization header
        actual_response = client.get("/students", headers=_JWT_HEADER)

        # THEN expect the response to be OK
        assert actual_response.status_code == HTTPStatus.OK
        # AND expect the items to be returned
        assert [item["id"] for item in actual_response.json()["data"]] == ["user-1"]
        # AND expect no institution scoping to be applied
        assert mocked_repository.list_users.call_args.kwargs["institution"] is None

    def test_returns_403_when_jwt_has_no_role(self):
        # GIVEN a JWT caller without an access role claim
        client, mocked_repository = _build_client(_user_info(role=None))

        # WHEN /students is called
        actual_response = client.get("/students", headers=_JWT_HEADER)

        # THEN expect the response to be FORBIDDEN
        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        # AND expect the repository to not be called
        mocked_repository.list_users.assert_not_called()

    def test_scopes_institution_staff_to_their_own_institution(self, institution_staff_client: TestClientWithMocks):
        # GIVEN an institution staff JWT caller
        client, mocked_repository = institution_staff_client

        # WHEN /students is called with a different institution filter
        actual_response = client.get("/students?institution=Other%20School", headers=_JWT_HEADER)

        # THEN expect the response to be OK
        assert actual_response.status_code == HTTPStatus.OK
        # AND expect the filter to be overridden with their own institution
        assert mocked_repository.list_users.call_args.kwargs["institution"] == "Staff School"


class TestListStudentsAnalyticsAuthentication:
    def test_returns_200_when_api_key_is_given(self, admin_client: TestClientWithMocks):
        # GIVEN a server-to-server caller with an x-api-key
        client, mocked_repository = admin_client

        # WHEN /students/analytics is called with the x-api-key header
        actual_response = client.get("/students/analytics", headers=_API_KEY_HEADER)

        # THEN expect the response to be OK
        assert actual_response.status_code == HTTPStatus.OK
        # AND expect the items to be returned
        assert [item["id"] for item in actual_response.json()["data"]] == ["user-1"]
        # AND expect no institution scoping to be applied
        assert mocked_repository.list_users.call_args.kwargs["institution"] is None

    def test_returns_403_when_no_api_key_is_given(self, admin_client: TestClientWithMocks):
        # GIVEN a caller without an api key
        client, mocked_repository = admin_client

        # WHEN /students/analytics is called without the x-api-key header
        actual_response = client.get("/students/analytics")

        # THEN expect the response to be FORBIDDEN
        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        # AND expect the repository to not be called
        mocked_repository.list_users.assert_not_called()

    def test_does_not_accept_a_jwt(self, admin_client: TestClientWithMocks):
        # GIVEN a caller with only a JWT
        client, mocked_repository = admin_client

        # WHEN /students/analytics is called with the Authorization header
        actual_response = client.get("/students/analytics", headers=_JWT_HEADER)

        # THEN expect the response to be FORBIDDEN
        assert actual_response.status_code == HTTPStatus.FORBIDDEN
        # AND expect the repository to not be called
        mocked_repository.list_users.assert_not_called()


class TestListStudentsAnalyticsInstitutionScoping:
    def test_decodes_encoded_institution_id(self, admin_client: TestClientWithMocks):
        # GIVEN a server-to-server caller
        client, mocked_repository = admin_client
        given_institution = _encode_institution_id("Test School")

        # WHEN /students/analytics is called with an encoded institution id
        actual_response = client.get(f"/students/analytics?institution={given_institution}", headers=_API_KEY_HEADER)

        # THEN expect the response to be OK
        assert actual_response.status_code == HTTPStatus.OK
        # AND expect the repository to be scoped to the decoded institution name
        assert mocked_repository.list_users.call_args.kwargs["institution"] == "Test School"

    def test_keeps_plain_institution_name(self, admin_client: TestClientWithMocks):
        # GIVEN a server-to-server caller
        client, mocked_repository = admin_client

        # WHEN /students/analytics is called with a plain (not encoded) institution name
        actual_response = client.get("/students/analytics?institution=Test%20School", headers=_API_KEY_HEADER)

        # THEN expect the response to be OK
        assert actual_response.status_code == HTTPStatus.OK
        # AND expect the repository to be scoped to that name as given
        assert mocked_repository.list_users.call_args.kwargs["institution"] == "Test School"


class TestListStudentsAnalyticsFilters:
    def test_passes_the_filters_and_pagination_to_the_repository(self, admin_client: TestClientWithMocks):
        # GIVEN a server-to-server caller
        client, mocked_repository = admin_client

        # WHEN /students/analytics is called with filters, pagination and include=count
        actual_response = client.get(
            "/students/analytics?active=true&province=Lusaka&programme=Carpentry&year=2&search=foo&limit=5&include=count",
            headers=_API_KEY_HEADER,
        )

        # THEN expect the response to be OK
        assert actual_response.status_code == HTTPStatus.OK
        # AND expect the filters to be forwarded to the repository
        actual_kwargs = mocked_repository.list_users.call_args.kwargs
        assert actual_kwargs["active"] is True
        assert actual_kwargs["province"] == "Lusaka"
        assert actual_kwargs["programme"] == "Carpentry"
        assert actual_kwargs["year"] == "2"
        assert actual_kwargs["search"] == "foo"
        assert actual_kwargs["limit"] == 5
        # AND expect the total to be included in the meta
        assert actual_response.json()["meta"]["total"] == 1

    def test_does_not_count_when_include_is_not_given(self, admin_client: TestClientWithMocks):
        # GIVEN a server-to-server caller
        client, mocked_repository = admin_client

        # WHEN /students/analytics is called without include=count
        actual_response = client.get("/students/analytics", headers=_API_KEY_HEADER)

        # THEN expect the response to be OK
        assert actual_response.status_code == HTTPStatus.OK
        # AND expect no count query to be issued
        mocked_repository.count_users.assert_not_called()
        # AND expect the total to be absent from the meta
        assert actual_response.json()["meta"]["total"] is None
