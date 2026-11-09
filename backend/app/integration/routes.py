import os
from http import HTTPStatus

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.app_config import get_application_config
from app.constants.errors import HTTPErrorResponse, HTTPExceptionWithErrorCode
from app.integration.firebase import get_integration_firebase
from app.integration.repository import ExternalUserRepository
from app.integration.return_url_validation import InvalidReturnUrlError
from app.integration.service import IntegrationService, ExternalUserConflictError, InvalidHandoffLinkError, \
    ExternalUserNotFoundError, ExternalUserResultsResponse, InvalidWebhookError
from app.integration.types import CreateExternalUserRequest, CreateExternalUserResponse, ExternalUserConflict, \
    HandoffExchangeRequest, HandoffExchangeResponse, EXTERNAL_ID_PATTERN
from app.server_dependencies.db_dependencies import CompassDBProvider
from app.store.database_application_state_store import DatabaseApplicationStateStore
from app.users.auth import ApiKeyAuth
from app.users.get_user_preferences_repository import get_user_preferences_repository
from app.users.preferences_service import IUserPreferencesService, get_user_preferences_service
from app.users.repositories import IUserPreferenceRepository

_CONFLICT_DETAILS = {
    ExternalUserConflict.EXTERNAL_ID_BOUND_TO_OTHER_EMAIL: "A user with this external_id already exists with another email.",
    ExternalUserConflict.EMAIL_BOUND_TO_OTHER_EXTERNAL_ID: "A user with this email already exists with another external_id.",
    ExternalUserConflict.ACCOUNT_ALREADY_EXISTS: "An account with this email already exists and was not created through this API.",
    ExternalUserConflict.ACCOUNT_NOT_ELIGIBLE: "The account of this user cannot be used through this API.",
}

INVALID_LINK_MESSAGE = "The link is not valid or has expired."
USER_NOT_FOUND_MESSAGE = "No user with this external_id."


async def get_integration_service(
        application_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_application_db),
        user_preferences_repository: IUserPreferenceRepository = Depends(get_user_preferences_repository),
        user_preferences_service: IUserPreferencesService = Depends(get_user_preferences_service),
) -> IntegrationService:
    app_config = get_application_config()
    return IntegrationService(
        user_repository=ExternalUserRepository(application_db),
        user_preferences_repository=user_preferences_repository,
        user_preferences_service=user_preferences_service,
        application_state_store=DatabaseApplicationStateStore(application_db),
        firebase=get_integration_firebase(),
        link_ttl_minutes=app_config.handoff_link_ttl_minutes,
        frontend_url=os.getenv("FRONTEND_URL", "").rstrip("/"),
        default_language=app_config.language_config.default_locale.value,
        return_url_origins=app_config.integration_return_url_origins,
        webhooks_enabled=app_config.integration_webhooks_enabled,
        webhook_url_origins=app_config.integration_webhook_url_origins,
    )


def add_integration_routes(app: FastAPI):
    """
    Add the integration routes:
    - POST /integration/users (API key): another platform creates a user and gets a hand-off link
    - GET /integration/users/{external_id}/results (API key): what the user's conversations produced
    - POST /handoff/exchange (no auth, the link token is the credential): the frontend exchanges the link for a login
    Like the other API key routes, /integration/users answers 403 to everyone while API_KEYS is empty.
    """
    integration_router = APIRouter(prefix="/integration", tags=["Integration"], dependencies=[Depends(ApiKeyAuth())])

    @integration_router.post(
        path="/users",
        status_code=HTTPStatus.CREATED,
        response_model=CreateExternalUserResponse,
        responses={
            HTTPStatus.OK: {"model": CreateExternalUserResponse,
                            "description": "The user already existed (same external_id and email)."},
            HTTPStatus.FORBIDDEN: {"model": HTTPErrorResponse, "description": "Missing or wrong x-api-key."},
            HTTPStatus.CONFLICT: {"model": HTTPErrorResponse,
                                  "description": "error_code: " + ", ".join(c.value for c in ExternalUserConflict)},
            HTTPStatus.UNPROCESSABLE_ENTITY: {
                "description": "Invalid body, a return_url or webhook_url that is not allowed, or a webhook_url while "
                               "webhooks are not enabled."},
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        name="create external user",
        description="Create a user (a Compass account for the calling platform's external_id and email) and a "
                    "hand-off link that logs them in. Re-submitting the same external_id and email is safe: it "
                    "returns 200 and a new link that replaces the old one.")
    async def _create_user(request: CreateExternalUserRequest, response: Response,
                           service: IntegrationService = Depends(get_integration_service)
                           ) -> CreateExternalUserResponse:
        try:
            created, body = await service.create_user(request)
        except ExternalUserConflictError as e:
            raise HTTPExceptionWithErrorCode(status_code=HTTPStatus.CONFLICT,
                                             detail=_CONFLICT_DETAILS[e.conflict],
                                             error_code=e.conflict.value) from e
        except (InvalidReturnUrlError, InvalidWebhookError) as e:
            raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(e)) from e
        response.status_code = HTTPStatus.CREATED if created else HTTPStatus.OK
        return body

    @integration_router.get(
        path="/users/{external_id}/results",
        response_model=ExternalUserResultsResponse,
        responses={
            HTTPStatus.FORBIDDEN: {"model": HTTPErrorResponse, "description": "Missing or wrong x-api-key."},
            HTTPStatus.NOT_FOUND: {"model": HTTPErrorResponse, "description": "No user with this external_id."},
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        name="get external user results",
        description="The results of the user's skills conversations, newest first: whether each is completed, and "
                    "the experiences explored with their skills. Always the current state: the user can still edit "
                    "their experiences after the conversation ends.")
    async def _get_results(external_id: str = Path(pattern=EXTERNAL_ID_PATTERN),
                           service: IntegrationService = Depends(get_integration_service)
                           ) -> ExternalUserResultsResponse:
        try:
            return await service.get_results(external_id)
        except ExternalUserNotFoundError as e:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=USER_NOT_FOUND_MESSAGE) from e

    handoff_router = APIRouter(prefix="/handoff", tags=["Integration"])

    @handoff_router.post(
        path="/exchange",
        response_model=HandoffExchangeResponse,
        responses={HTTPStatus.UNAUTHORIZED: {"model": HTTPErrorResponse},
                   HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse}},
        name="exchange hand-off link",
        description="Exchange the token of a hand-off link for a Firebase custom token. Unknown, expired and "
                    "replaced links get the same 401.")
    async def _exchange_link(request: HandoffExchangeRequest,
                             service: IntegrationService = Depends(get_integration_service)
                             ) -> HandoffExchangeResponse:
        try:
            return await service.exchange_link(request.token)
        except InvalidHandoffLinkError as e:
            raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail=INVALID_LINK_MESSAGE) from e

    app.include_router(integration_router)
    app.include_router(handoff_router)
