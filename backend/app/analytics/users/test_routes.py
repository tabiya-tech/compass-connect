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
from app.users.auth import SignInProvider, UserInfo
from common_libs.test_utilities.mock_auth import MockAuth

TestClientWithMocks = tuple[TestClient, UserRepository]

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
    add_users_routes(router, MockAuth(user_info))
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
