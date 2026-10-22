"""
This module contains the service layer for the user preferences.
"""
from abc import ABC, abstractmethod

from fastapi import Depends

from app.metrics.services.get_metrics_service import get_metrics_service
from app.metrics.services.service import IMetricsService
from app.metrics.types import UserAccountCreatedEvent
from app.users.generate_session_id import generate_new_session_id
from app.users.get_user_preferences_repository import get_user_preferences_repository
from app.users.repositories import IUserPreferenceRepository
from app.users.sensitive_personal_data.types import SensitivePersonalDataRequirement
from app.users.types import UserPreferences


class IUserPreferencesService(ABC):
    """
    Interface for the User Preferences Service

    Allows to mock the service in tests.
    """

    @abstractmethod
    async def create_new_user_preferences(self, *,
                                          user_id: str,
                                          language: str | None,
                                          invitation_code: str | None,
                                          client_id: str | None,
                                          sensitive_personal_data_requirement: SensitivePersonalDataRequirement
                                          ) -> UserPreferences:
        """
        Create the preferences of a new user, with their first conversation session, and record the account creation.
        Shared by the registration route (POST /users/preferences) and the integration API, which creates the user on
        the server.

        :return: UserPreferences - the newly created preferences
        :raises UserPreferenceRepositoryError: if the insert fails, e.g. the preferences of the user already exist
        :raises Exception: if any other error occurs
        """
        raise NotImplementedError()


class UserPreferencesService(IUserPreferencesService):
    def __init__(self, repository: IUserPreferenceRepository, metrics_service: IMetricsService):
        self._repository = repository
        self._metrics_service = metrics_service

    async def create_new_user_preferences(self, *,
                                          user_id: str,
                                          language: str | None,
                                          invitation_code: str | None,
                                          client_id: str | None,
                                          sensitive_personal_data_requirement: SensitivePersonalDataRequirement
                                          ) -> UserPreferences:
        # Generating a 64-bit integer session ID
        sessions = [generate_new_session_id()]

        newly_created = await self._repository.insert_user_preference(user_id, UserPreferences(
            language=language,
            invitation_code=invitation_code,
            client_id=client_id,
            sensitive_personal_data_requirement=sensitive_personal_data_requirement,
            sessions=sessions
        ))

        # Record user account creation metric
        await self._metrics_service.record_event(UserAccountCreatedEvent(
            user_id=user_id,
            client_id=client_id,
        ))

        return newly_created


async def get_user_preferences_service(
        repository: IUserPreferenceRepository = Depends(get_user_preferences_repository),
        metrics_service: IMetricsService = Depends(get_metrics_service)) -> IUserPreferencesService:
    return UserPreferencesService(repository, metrics_service)
