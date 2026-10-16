from app.metrics.services.service import IMetricsService
from app.metrics.types import UserAccountCreatedEvent
from app.users.generate_session_id import generate_new_session_id
from app.users.repositories import IUserPreferenceRepository
from app.users.sensitive_personal_data.types import SensitivePersonalDataRequirement
from app.users.types import UserPreferences


async def create_new_user_preferences(*,
                                      repository: IUserPreferenceRepository,
                                      metrics_service: IMetricsService,
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
    """
    # Generating a 64-bit integer session ID
    sessions = [generate_new_session_id()]

    newly_created = await repository.insert_user_preference(user_id, UserPreferences(
        language=language,
        invitation_code=invitation_code,
        client_id=client_id,
        sensitive_personal_data_requirement=sensitive_personal_data_requirement,
        sessions=sessions
    ))

    # Record user account creation metric
    await metrics_service.record_event(UserAccountCreatedEvent(
        user_id=user_id,
        client_id=client_id,
    ))

    return newly_created
