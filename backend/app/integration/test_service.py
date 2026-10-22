from dataclasses import dataclass, field
from datetime import timedelta
from typing import Awaitable, Optional
from unittest.mock import AsyncMock

import pytest
import pytest_mock
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.metrics.services.service import IMetricsService
from app.metrics.types import UserAccountCreatedEvent
from app.integration.repository import ExternalUserRepository
from app.integration.service import IntegrationService, ExternalUserConflictError, InvalidHandoffLinkError, \
    hash_link_token
from app.integration.types import CreateExternalUserRequest, HandoffAction, ExternalUserConflict, HandoffLink, \
    ExternalUser
from app.users.repositories import UserPreferenceRepository
from app.users.preferences_service import UserPreferencesService
from app.users.sensitive_personal_data.types import SensitivePersonalDataRequirement
from common_libs.time_utilities import get_now

_FRONTEND_URL = "https://compass.example.org"
_TTL_MINUTES = 60


@dataclass
class _FakeUser:
    uid: str
    email: str
    custom_claims: Optional[dict] = None
    disabled: bool = False


@dataclass
class _FakeFirebase:
    """ The Firebase calls of IntegrationFirebase, on an in-memory user pool. """
    users: dict[str, _FakeUser] = field(default_factory=dict)
    created_emails: list[str] = field(default_factory=list)

    def add_user(self, email: str, **kwargs) -> _FakeUser:
        user = _FakeUser(uid=f"uid-{len(self.users) + 1}", email=email, **kwargs)
        self.users[user.uid] = user
        return user

    def get_user_by_email(self, email: str) -> Optional[_FakeUser]:
        return next((u for u in self.users.values() if u.email == email), None)

    def get_user(self, user_id: str) -> Optional[_FakeUser]:
        return self.users.get(user_id)

    def create_user(self, email: str) -> _FakeUser:
        self.created_emails.append(email)
        return self.add_user(email)

    def create_custom_token(self, user_id: str) -> str:
        return f"custom-token-for-{user_id}"


@dataclass
class _Setup:
    service: IntegrationService
    firebase: _FakeFirebase
    users: ExternalUserRepository
    user_preferences: UserPreferenceRepository
    metrics_service: AsyncMock


@pytest.fixture(scope="function")
async def setup(in_memory_application_database: Awaitable[AsyncIOMotorDatabase],
                setup_application_config) -> _Setup:
    # the metric events read the application config
    db = await in_memory_application_database
    firebase = _FakeFirebase()
    users = ExternalUserRepository(db)
    user_preferences = UserPreferenceRepository(db)
    metrics_service = AsyncMock(spec=IMetricsService)
    service = IntegrationService(
        user_repository=users,
        user_preferences_repository=user_preferences,
        user_preferences_service=UserPreferencesService(user_preferences, metrics_service),
        firebase=firebase,  # type: ignore[arg-type]
        link_ttl_minutes=_TTL_MINUTES,
        frontend_url=_FRONTEND_URL,
        default_language="es-ES",
    )
    return _Setup(service, firebase, users, user_preferences, metrics_service)


def _request(external_id: str = "ext-1", email: str = "person@example.com",
             action: HandoffAction = HandoffAction.BUILD_PROFILE) -> CreateExternalUserRequest:
    return CreateExternalUserRequest(external_id=external_id, email=email, action=action)


def _token_of(url: str) -> str:
    return url.split("token=", 1)[1]


async def _assert_conflict(s: _Setup, request: CreateExternalUserRequest, expected: ExternalUserConflict):
    with pytest.raises(ExternalUserConflictError) as e:
        await s.service.create_user(request)
    assert e.value.conflict == expected


class TestCreateUser:
    @pytest.mark.asyncio
    async def test_new_user(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a user the instance does not know
        given_request = _request()

        # WHEN the platform creates it
        actual_created, actual = await s.service.create_user(given_request)

        # THEN it is reported as created
        assert actual_created is True
        assert actual.user.external_id == "ext-1"
        assert actual.user.email == "person@example.com"
        # AND a Firebase account was created for its email, and recorded on the user
        assert s.firebase.created_emails == ["person@example.com"]
        actual_user = s.firebase.get_user_by_email("person@example.com")
        assert (await s.users.find_by_external_id("ext-1")).user_id == actual_user.uid
        # AND the preferences were created like a registration: default language, one session, consent not given
        actual_preferences = await s.user_preferences.get_user_preference_by_user_id(actual_user.uid)
        assert actual_preferences.language == "es-ES"
        assert len(actual_preferences.sessions) == 1
        assert actual_preferences.accepted_tc is None
        assert actual_preferences.invitation_code is None
        assert actual_preferences.sensitive_personal_data_requirement == \
            SensitivePersonalDataRequirement.NOT_AVAILABLE.value
        # AND the account creation was recorded
        s.metrics_service.record_event.assert_awaited_once()
        actual_event = s.metrics_service.record_event.await_args.args[0]
        assert isinstance(actual_event, UserAccountCreatedEvent)
        # AND an hand-off link to the frontend was issued, valid for the configured time
        assert actual.link.url.startswith(f"{_FRONTEND_URL}/#/handoff?token=")
        assert len(_token_of(actual.link.url)) >= 40
        assert abs(actual.link.expires_at - (get_now() + timedelta(minutes=_TTL_MINUTES))) < timedelta(seconds=30)

    @pytest.mark.asyncio
    async def test_resubmit_is_idempotent_and_replaces_the_link(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a user created with a link
        _, given_first = await s.service.create_user(_request())

        # WHEN the platform sends the same user again
        actual_created, actual = await s.service.create_user(_request())

        # THEN it is reported as existing, with the original creation time
        assert actual_created is False
        assert actual.user.created_at == given_first.user.created_at
        # AND no second account or preferences were created
        assert s.firebase.created_emails == ["person@example.com"]
        s.metrics_service.record_event.assert_awaited_once()
        # AND the new link works and the old one no longer does
        assert actual.link.url != given_first.link.url
        await s.service.exchange_link(_token_of(actual.link.url))
        with pytest.raises(InvalidHandoffLinkError):
            await s.service.exchange_link(_token_of(given_first.link.url))

    @pytest.mark.asyncio
    async def test_email_is_matched_case_insensitively(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a user created with a lowercase email
        await s.service.create_user(_request(email="person@example.com"))

        # WHEN it is sent again with different case and spaces
        actual_created, _ = await s.service.create_user(_request(email="  Person@Example.COM "))

        # THEN it is the same user
        assert actual_created is False

    @pytest.mark.asyncio
    async def test_external_id_with_other_email_is_a_conflict(self, setup: Awaitable[_Setup]):
        s = await setup
        await s.service.create_user(_request(external_id="ext-1", email="person@example.com"))
        await _assert_conflict(s, _request(external_id="ext-1", email="other@example.com"),
                               ExternalUserConflict.EXTERNAL_ID_BOUND_TO_OTHER_EMAIL)

    @pytest.mark.asyncio
    async def test_email_with_other_external_id_is_a_conflict(self, setup: Awaitable[_Setup]):
        s = await setup
        await s.service.create_user(_request(external_id="ext-1", email="person@example.com"))
        await _assert_conflict(s, _request(external_id="ext-2", email="person@example.com"),
                               ExternalUserConflict.EMAIL_BOUND_TO_OTHER_EXTERNAL_ID)

    @pytest.mark.asyncio
    async def test_existing_account_not_created_by_the_api_is_refused(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN an account that signed up by itself
        s.firebase.add_user("person@example.com")

        # WHEN the platform creates a user with that email
        # THEN it is refused
        await _assert_conflict(s, _request(), ExternalUserConflict.ACCOUNT_ALREADY_EXISTS)
        # AND nothing was recorded, so a later request is refused too
        assert await s.users.find_by_external_id("ext-1") is None

    @pytest.mark.asyncio
    async def test_existing_admin_account_is_refused(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN an admin account with the email
        s.firebase.add_user("person@example.com", custom_claims={"role": "admin"})

        # WHEN the platform creates a user with that email
        # THEN it is refused
        await _assert_conflict(s, _request(), ExternalUserConflict.ACCOUNT_ALREADY_EXISTS)

    @pytest.mark.asyncio
    async def test_retry_after_a_half_finished_request_completes_it(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN an earlier request that recorded the user and created its account, then failed
        now = get_now()
        await s.users.insert(ExternalUser(external_id="ext-1", email="person@example.com",
                                          created_at=now, updated_at=now))
        given_user = s.firebase.add_user("person@example.com")

        # WHEN the platform retries
        actual_created, actual = await s.service.create_user(_request())

        # THEN the user is completed with that account, without creating another one
        assert actual_created is False
        assert (await s.users.find_by_external_id("ext-1")).user_id == given_user.uid
        assert s.firebase.created_emails == []
        assert await s.user_preferences.get_user_preference_by_user_id(given_user.uid) is not None
        assert actual.link is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_change", [
        pytest.param({"custom_claims": {"role": "admin"}}, id="given custom claims"),
        pytest.param({"disabled": True}, id="disabled"),
    ])
    async def test_account_changed_after_creation_is_not_eligible(self, setup: Awaitable[_Setup],
                                                                  given_change: dict):
        s = await setup
        # GIVEN a user whose account was later given custom claims, or disabled
        await s.service.create_user(_request())
        given_user = s.firebase.get_user_by_email("person@example.com")
        for key, value in given_change.items():
            setattr(given_user, key, value)

        # WHEN the platform sends it again
        # THEN it is refused
        await _assert_conflict(s, _request(), ExternalUserConflict.ACCOUNT_NOT_ELIGIBLE)

    @pytest.mark.asyncio
    async def test_account_deleted_after_creation_is_not_eligible(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a user whose account was deleted in Firebase
        await s.service.create_user(_request())
        s.firebase.users.clear()

        # WHEN the platform sends it again
        # THEN it is refused
        await _assert_conflict(s, _request(), ExternalUserConflict.ACCOUNT_NOT_ELIGIBLE)

    @pytest.mark.asyncio
    async def test_concurrent_request_for_the_same_user(self, setup: Awaitable[_Setup],
                                                        mocker: pytest_mock.MockerFixture):
        s = await setup
        # GIVEN a concurrent request recorded the same user between our lookup and our insert
        now = get_now()
        await s.users.insert(ExternalUser(external_id="ext-1", email="person@example.com",
                                          created_at=now, updated_at=now))
        original_find = s.users.find_by_external_id
        mocker.patch.object(s.users, "find_by_external_id",
                            side_effect=[None, await original_find("ext-1")])
        mocker.patch.object(s.users, "find_by_email", return_value=None)

        # WHEN this request goes on
        actual_created, actual = await s.service.create_user(_request())

        # THEN it uses that user
        assert actual_created is False
        assert actual.user.created_at == (await original_find("ext-1")).created_at


class TestExchangeLink:
    @pytest.mark.asyncio
    async def test_link_is_reusable_until_it_expires(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a user with a link to the conversation
        _, given = await s.service.create_user(_request())
        given_token = _token_of(given.link.url)
        given_user = s.firebase.get_user_by_email("person@example.com")

        # WHEN the link is opened twice
        actual_first = await s.service.exchange_link(given_token)
        actual_second = await s.service.exchange_link(given_token)

        # THEN both give a custom token for the user and the landing action
        for actual in (actual_first, actual_second):
            assert actual.custom_token == f"custom-token-for-{given_user.uid}"
            assert actual.action == HandoffAction.BUILD_PROFILE

    @pytest.mark.asyncio
    async def test_create_action_is_returned(self, setup: Awaitable[_Setup]):
        s = await setup
        _, given = await s.service.create_user(_request(action=HandoffAction.CREATE))
        assert (await s.service.exchange_link(_token_of(given.link.url))).action == HandoffAction.CREATE

    @pytest.mark.asyncio
    async def test_unknown_token_is_invalid(self, setup: Awaitable[_Setup]):
        s = await setup
        with pytest.raises(InvalidHandoffLinkError):
            await s.service.exchange_link("not-a-real-token")

    @pytest.mark.asyncio
    async def test_expired_link_is_invalid(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN an existing user whose link has expired
        await s.service.create_user(_request())
        await s.users.set_link("ext-1", HandoffLink(token_hash=hash_link_token("expired-token"),
                                                    action=HandoffAction.BUILD_PROFILE,
                                                    expires_at=get_now() - timedelta(days=1)), get_now())

        # WHEN it is opened
        # THEN it is invalid
        with pytest.raises(InvalidHandoffLinkError):
            await s.service.exchange_link("expired-token")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_change", [
        pytest.param({"custom_claims": {"role": "admin"}}, id="given custom claims"),
        pytest.param({"disabled": True}, id="disabled"),
    ])
    async def test_account_changed_after_the_link_was_issued(self, setup: Awaitable[_Setup], given_change: dict):
        s = await setup
        # GIVEN a link, then the account is given custom claims or disabled
        _, given = await s.service.create_user(_request())
        given_user = s.firebase.get_user_by_email("person@example.com")
        for key, value in given_change.items():
            setattr(given_user, key, value)

        # WHEN the link is opened
        # THEN it is invalid
        with pytest.raises(InvalidHandoffLinkError):
            await s.service.exchange_link(_token_of(given.link.url))

    @pytest.mark.asyncio
    async def test_account_deleted_after_the_link_was_issued(self, setup: Awaitable[_Setup]):
        s = await setup
        _, given = await s.service.create_user(_request())
        s.firebase.users.clear()
        with pytest.raises(InvalidHandoffLinkError):
            await s.service.exchange_link(_token_of(given.link.url))
