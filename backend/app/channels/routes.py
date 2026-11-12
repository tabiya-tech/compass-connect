import logging
import re
from http import HTTPStatus

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.app_config import get_application_config
from app.channels.repository import ChannelStateRepository
from app.channels.service import ChannelGatewayService, ChannelUserNotFoundError, IChannelGatewayService
from app.channels.types import CHANNEL_USER_ID_PATTERN, IncomingMessage, InitializeConversationRequest, \
    OutgoingMessage
from app.constants.errors import HTTPErrorResponse
from app.conversations.routes import get_conversation_service
from app.conversations.service import IConversationService
from app.metrics.services.get_metrics_service import get_metrics_service
from app.metrics.services.service import IMetricsService
from app.server_dependencies.db_dependencies import CompassDBProvider
from app.users.auth import ApiKeyAuth
from app.users.get_user_preferences_repository import get_user_preferences_repository
from app.users.plain_personal_data.routes import get_plain_personal_data_service
from app.users.plain_personal_data.service import IPlainPersonalDataService
from app.users.preferences_service import IUserPreferencesService, get_user_preferences_service
from app.users.repositories import IUserPreferenceRepository

CHANNEL_USER_NOT_FOUND_MESSAGE = "No conversation for this channel user, initialize the conversation first."
CHANNEL_USER_ID_MISMATCH_MESSAGE = "The channel_user_id of the path and of the body are not the same."

_CHANNEL_USER_ID_IN_PATH = re.compile(r"^(/api/channels/conversations/)[^/?#]+")


class ChannelUserIdRedactionFilter(logging.Filter):
    """
    Removes the channel user id from the path of the access log lines (uvicorn.access), as it is personal data.
    The args of an access log record are (client address, method, path, http version, status code).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            redacted_path = _CHANNEL_USER_ID_IN_PATH.sub(r"\1<redacted>", args[2])
            if redacted_path != args[2]:
                record.args = args[:2] + (redacted_path,) + args[3:]
        return True


async def get_channel_gateway_service(
        user_preferences_repository: IUserPreferenceRepository = Depends(get_user_preferences_repository),
        user_preferences_service: IUserPreferencesService = Depends(get_user_preferences_service),
        conversation_service: IConversationService = Depends(get_conversation_service),
        plain_personal_data_service: IPlainPersonalDataService = Depends(get_plain_personal_data_service),
        application_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_application_db),
        metrics_service: IMetricsService = Depends(get_metrics_service),
) -> IChannelGatewayService:
    app_config = get_application_config()
    return ChannelGatewayService(
        user_preferences_repository=user_preferences_repository,
        user_preferences_service=user_preferences_service,
        conversation_service=conversation_service,
        plain_personal_data_service=plain_personal_data_service,
        channel_state_repository=ChannelStateRepository(application_db),
        metrics_service=metrics_service,
        default_language=app_config.language_config.default_locale.value,
    )


def add_channels_routes(app: FastAPI):
    """
    Add the channels routes, called by the chat bots (Telegram, WhatsApp) with an API key, not a Firebase token:
    - POST /api/channels/conversations: find or create the anonymous user of a channel user, and get the welcome
      message
    - POST /api/channels/conversations/{channel_user_id}/messages: send a message of the user, and get the replies
    Like the other API key routes, they answer 403 to everyone while API_KEYS is empty (INGRESS_MODE=direct).
    """
    # the channel user id is in the path of the messages route: keep it out of the access logs
    logging.getLogger("uvicorn.access").addFilter(ChannelUserIdRedactionFilter())

    router = APIRouter(prefix="/api/channels", tags=["Channels"], dependencies=[Depends(ApiKeyAuth())])

    @router.post(
        path="/conversations",
        response_model=list[OutgoingMessage],
        responses={
            HTTPStatus.FORBIDDEN: {"model": HTTPErrorResponse, "description": "Missing or wrong x-api-key."},
            HTTPStatus.UNPROCESSABLE_ENTITY: {"description": "Invalid body."},
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        name="initialize channel conversation",
        description="Find or create the anonymous Compass user of the channel user (with their preferences and a "
                    "session), and get the welcome message. For now the terms are accepted for the user when the "
                    "conversation is initialized. Calling it again for the same channel user reuses their Compass "
                    "user.")
    async def _initialize_conversation(request: InitializeConversationRequest,
                                       service: IChannelGatewayService = Depends(get_channel_gateway_service)
                                       ) -> list[OutgoingMessage]:
        return await service.initialize_conversation(request.channel, request.channel_user_id)

    @router.post(
        path="/conversations/{channel_user_id}/messages",
        response_model=list[OutgoingMessage],
        responses={
            HTTPStatus.FORBIDDEN: {"model": HTTPErrorResponse, "description": "Missing or wrong x-api-key."},
            HTTPStatus.NOT_FOUND: {"model": HTTPErrorResponse, "description": CHANNEL_USER_NOT_FOUND_MESSAGE},
            HTTPStatus.UNPROCESSABLE_ENTITY: {"description": "Invalid body, or a channel_user_id that is not the "
                                                             "one of the path."},
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        name="send channel message",
        description="Send a message (typed text or a command) the user sent on the channel, and get the messages to "
                    "send them back. The text goes to the user's Compass conversation. The commands are /start, "
                    "/restart, /report and /help. An error of the conversation (e.g. a conversation that already "
                    "ended) is a message to the user, not an error status.")
    async def _send_message(message: IncomingMessage,
                            channel_user_id: str = Path(pattern=CHANNEL_USER_ID_PATTERN),
                            service: IChannelGatewayService = Depends(get_channel_gateway_service)
                            ) -> list[OutgoingMessage]:
        if message.channel_user_id != channel_user_id:
            raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=CHANNEL_USER_ID_MISMATCH_MESSAGE)
        try:
            return await service.handle_sent_message(message)
        except ChannelUserNotFoundError as e:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=CHANNEL_USER_NOT_FOUND_MESSAGE) from e

    app.include_router(router)
