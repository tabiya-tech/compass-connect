"""
Tests for the PlainPersonalDataService class.
"""
from typing import Optional

import pytest

from app.users.plain_personal_data.errors import UserPreferencesNotFoundError
from app.users.plain_personal_data.repository import IPlainPersonalDataRepository
from app.users.plain_personal_data.service import PlainPersonalDataService
from app.users.plain_personal_data.types import PlainPersonalData
from app.users.repositories import IUserPreferenceRepository
from app.users.sensitive_personal_data.types import SensitivePersonalDataRequirement
from app.users.types import UserPreferences, UserPreferencesRepositoryUpdateRequest
from common_libs.test_utilities.random_data import get_random_printable_string


def _make_mock_plain_personal_data_repository(find_result: Optional[PlainPersonalData] = None) -> IPlainPersonalDataRepository:
    class MockRepo(IPlainPersonalDataRepository):
        def __init__(self):
            self.upsert_calls = []

        async def find_by_user_id(self, user_id: str) -> Optional[PlainPersonalData]:
            return find_result

        async def upsert(self, user_id: str, data: dict) -> None:
            self.upsert_calls.append((user_id, data))

    return MockRepo()


def _make_mock_user_preference_repository(prefs: Optional[UserPreferences] = None) -> IUserPreferenceRepository:
    class MockUserPreferenceRepo(IUserPreferenceRepository):
        async def get_user_preference_by_user_id(self, user_id: str) -> Optional[UserPreferences]:
            return prefs

        async def get_user_preference_by_channel_user_id(self, channel, channel_user_id: str):
            raise NotImplementedError()

        async def update_user_preference(self, user_id: str, request: UserPreferencesRepositoryUpdateRequest) -> Optional[UserPreferences]:
            raise NotImplementedError

        async def insert_user_preference(self, user_id: str, user_preference: UserPreferences) -> UserPreferences:
            raise NotImplementedError

        async def get_experiments_by_user_id(self, user_id: str) -> dict[str, str]:
            raise NotImplementedError

        async def get_experiments_by_user_ids(self, user_ids: list[str]) -> dict[str, dict[str, str]]:
            raise NotImplementedError

        async def set_experiment_by_user_id(self, user_id: str, experiment_id: str, experiment_class: str) -> None:
            raise NotImplementedError

    return MockUserPreferenceRepo()


class TestUpsert:
    @pytest.mark.asyncio
    async def test_raises_user_preferences_not_found_when_user_has_no_preferences(self):
        # GIVEN a user without preferences
        given_user_id = get_random_printable_string(10)
        mock_repo = _make_mock_plain_personal_data_repository()
        mock_pref_repo = _make_mock_user_preference_repository(prefs=None)
        service = PlainPersonalDataService(mock_repo, mock_pref_repo)

        # WHEN upsert is called
        # THEN UserPreferencesNotFoundError is raised
        with pytest.raises(UserPreferencesNotFoundError):
            await service.upsert(given_user_id, {"age": "25"})

    @pytest.mark.asyncio
    async def test_calls_repository_upsert_when_user_preferences_exist(self):
        # GIVEN a user with valid preferences
        given_user_id = get_random_printable_string(10)
        given_data = {"age": "30"}
        mock_repo = _make_mock_plain_personal_data_repository()
        mock_pref_repo = _make_mock_user_preference_repository(prefs=UserPreferences(
            sensitive_personal_data_requirement=SensitivePersonalDataRequirement.NOT_REQUIRED,
        ))
        service = PlainPersonalDataService(mock_repo, mock_pref_repo)

        # WHEN upsert is called
        await service.upsert(given_user_id, given_data)

        # THEN the repository upsert is called with the correct arguments
        assert (given_user_id, given_data) in mock_repo.upsert_calls


class TestGet:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_data_found(self):
        # GIVEN no data exists for the user
        given_user_id = get_random_printable_string(10)
        mock_repo = _make_mock_plain_personal_data_repository(find_result=None)
        mock_pref_repo = _make_mock_user_preference_repository()
        service = PlainPersonalDataService(mock_repo, mock_pref_repo)

        # WHEN get is called
        result = await service.get(given_user_id)

        # THEN None is returned
        assert result is None
