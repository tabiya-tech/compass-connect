from datetime import timedelta
from typing import Awaitable

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.integration.repository import ExternalUserRepository, DuplicateExternalUserError
from app.integration.types import ExternalUser, HandoffLink, HandoffAction
from common_libs.time_utilities import get_now, truncate_microseconds


@pytest.fixture(scope="function")
async def repository(in_memory_application_database: Awaitable[AsyncIOMotorDatabase]) -> ExternalUserRepository:
    return ExternalUserRepository(await in_memory_application_database)


def _user(external_id: str = "ext-1", email: str = "person@example.com", user_id: str | None = None) -> ExternalUser:
    # MongoDB keeps milliseconds only
    now = truncate_microseconds(get_now())
    return ExternalUser(external_id=external_id, email=email, user_id=user_id, created_at=now, updated_at=now)


def _link(token_hash: str = "hash-1", expires_in: timedelta = timedelta(hours=1)) -> HandoffLink:  # nosec B107 # test fixture, not a credential
    return HandoffLink(token_hash=token_hash, action=HandoffAction.BUILD_PROFILE,
                       expires_at=truncate_microseconds(get_now() + expires_in))


class TestExternalUserRepository:
    @pytest.mark.asyncio
    async def test_insert_and_find(self, repository: Awaitable[ExternalUserRepository]):
        repository = await repository
        # GIVEN a user without a Firebase account yet
        given_user = _user()

        # WHEN it is inserted
        await repository.insert(given_user)

        # THEN it is found by external id and by email
        assert await repository.find_by_external_id("ext-1") == given_user
        assert await repository.find_by_email("person@example.com") == given_user
        # AND unknown ones are not found
        assert await repository.find_by_external_id("ext-2") is None
        assert await repository.find_by_email("other@example.com") is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_duplicate", [
        pytest.param(_user(email="other@example.com"), id="same external id"),
        pytest.param(_user(external_id="ext-2"), id="same email"),
    ])
    async def test_insert_duplicate_is_refused(self, repository: Awaitable[ExternalUserRepository],
                                               given_duplicate: ExternalUser):
        repository = await repository
        # GIVEN an existing user
        await repository.insert(_user())

        # WHEN another one with the same external id or email is inserted
        # THEN it is refused
        with pytest.raises(DuplicateExternalUserError):
            await repository.insert(given_duplicate)

    @pytest.mark.asyncio
    async def test_users_without_user_id_or_link_do_not_collide(self, repository: Awaitable[ExternalUserRepository]):
        repository = await repository
        # GIVEN two users without a Firebase account or a link yet
        # WHEN both are inserted
        await repository.insert(_user(external_id="ext-1", email="one@example.com"))
        await repository.insert(_user(external_id="ext-2", email="two@example.com"))

        # THEN both exist (only set user ids and token hashes have to be unique)
        assert await repository.find_by_external_id("ext-1") is not None
        assert await repository.find_by_external_id("ext-2") is not None

    @pytest.mark.asyncio
    async def test_set_user_id(self, repository: Awaitable[ExternalUserRepository]):
        repository = await repository
        # GIVEN a user without a Firebase account yet
        await repository.insert(_user())

        # WHEN its user id is set
        given_updated_at = truncate_microseconds(get_now() + timedelta(minutes=1))
        await repository.set_user_id("ext-1", "user-1", given_updated_at)

        # THEN the user has it
        actual = await repository.find_by_external_id("ext-1")
        assert actual.user_id == "user-1"
        assert actual.updated_at == given_updated_at

    @pytest.mark.asyncio
    async def test_same_user_id_on_two_users_is_refused(self, repository: Awaitable[ExternalUserRepository]):
        repository = await repository
        # GIVEN a user with a user id and another one without
        await repository.insert(_user(external_id="ext-1", email="one@example.com", user_id="user-1"))
        await repository.insert(_user(external_id="ext-2", email="two@example.com"))

        # WHEN the second one gets the same user id
        # THEN it is refused
        with pytest.raises(DuplicateKeyError):
            await repository.set_user_id("ext-2", "user-1", get_now())

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_set", [
        pytest.param(lambda r: r.set_user_id("unknown", "user-1", get_now()), id="user id"),
        pytest.param(lambda r: r.set_link("unknown", _link(), get_now()), id="link"),
    ])
    async def test_set_on_unknown_user_fails(self, repository: Awaitable[ExternalUserRepository], given_set):
        repository = await repository
        with pytest.raises(ValueError):
            await given_set(repository)

    @pytest.mark.asyncio
    async def test_find_by_valid_link(self, repository: Awaitable[ExternalUserRepository]):
        repository = await repository
        # GIVEN a user with a live link
        await repository.insert(_user(user_id="user-1"))
        given_link = _link()
        await repository.set_link("ext-1", given_link, get_now())

        # WHEN the user is looked up by the token hash of the link
        actual = await repository.find_by_valid_link("hash-1", get_now())

        # THEN it is found, with the link
        assert actual.external_id == "ext-1"
        assert actual.link == given_link
        # AND an unknown hash is not
        assert await repository.find_by_valid_link("unknown", get_now()) is None

    @pytest.mark.asyncio
    async def test_expired_link_is_not_valid(self, repository: Awaitable[ExternalUserRepository]):
        repository = await repository
        # GIVEN a user whose link has expired
        await repository.insert(_user(user_id="user-1"))
        await repository.set_link("ext-1", _link(expires_in=timedelta(seconds=-1)), get_now())

        # WHEN the user is looked up by the token hash of the link
        # THEN it is not found
        assert await repository.find_by_valid_link("hash-1", get_now()) is None

    @pytest.mark.asyncio
    async def test_new_link_replaces_the_old_one(self, repository: Awaitable[ExternalUserRepository]):
        repository = await repository
        # GIVEN a user with a link
        await repository.insert(_user(user_id="user-1"))
        await repository.set_link("ext-1", _link(token_hash="hash-1"), get_now())  # nosec B106 # test fixture

        # WHEN a new link is set
        await repository.set_link("ext-1", _link(token_hash="hash-2"), get_now())  # nosec B106 # test fixture

        # THEN only the new one is valid
        assert await repository.find_by_valid_link("hash-1", get_now()) is None
        assert await repository.find_by_valid_link("hash-2", get_now()) is not None
