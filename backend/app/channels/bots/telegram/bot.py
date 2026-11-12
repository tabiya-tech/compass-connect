import hashlib
import hmac
import json
from http import HTTPStatus
from typing import Optional

import sentry_sdk
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from telegram import Bot, InputFile, Update
from telegram.constants import ChatAction
from telegram.error import TelegramError

from app.channels.bots.bot import ChannelBot, DocumentDownloader, download_document
from app.channels.bots.tasks import BackgroundTasks
from app.channels.bots.telegram.config import WEBHOOK_PATH, TelegramConfig
from app.channels.bots.telegram.mapping import COMMANDS, build_reply_markup, to_incoming_event
from app.channels.observability import ChannelOperation, capture_gateway_error, set_channel_context
from app.channels.repository import ChannelStateRepository, IChannelStateRepository
from app.channels.routes import get_channel_gateway_service
from app.channels.service import IChannelGatewayService
from app.channels.types import Channel
from app.i18n.types import Locale
from app.metrics.services.service import IMetricsService
from app.metrics.types import BotInitializedEvent, BotRegistrationStatus
from app.server_dependencies.db_dependencies import CompassDBProvider

MAX_TEXT_LENGTH = 4096
""" The longest message Telegram accepts. """

MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
""" The largest file a bot can upload to Telegram. """

SECRET_TOKEN_HEADER = "X-Telegram-Bot-Api-Secret-Token"  # nosec B105 # the name of the header, not a secret

ALLOWED_UPDATES = [Update.MESSAGE]
""" The updates Telegram sends: new messages only. """

SHUTDOWN_TIMEOUT_SECONDS = 8.0
""" How long to wait for the turns in progress on shutdown. Cloud Run gives 10 seconds after SIGTERM. """


async def get_channel_state_repository(
        application_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_application_db)
) -> IChannelStateRepository:
    return ChannelStateRepository(application_db)


class TelegramBot(ChannelBot):
    """
    Receives the Telegram updates on a webhook, and sends the messages with the Telegram Bot API.

    The webhook answers at once, and handles the update in the background: a conversation turn can take longer than
    Telegram waits for the webhook, and Telegram would send the update again.
    """

    def __init__(self, *,
                 config: TelegramConfig,
                 default_locale: Locale,
                 bot: Optional[Bot] = None,
                 background_tasks: Optional[BackgroundTasks] = None,
                 typing_interval_seconds: float = 4.0,
                 document_downloader: DocumentDownloader = download_document):
        super().__init__(default_locale=default_locale,
                         typing_interval_seconds=typing_interval_seconds, document_downloader=document_downloader)
        self._config = config
        self._bot = bot or Bot(config.bot_token)
        self._background_tasks = background_tasks or BackgroundTasks()

    @property
    def channel(self) -> Channel:
        return Channel.TELEGRAM

    @property
    def max_text_length(self) -> int:
        return MAX_TEXT_LENGTH

    @property
    def max_document_bytes(self) -> Optional[int]:
        return MAX_DOCUMENT_BYTES

    @property
    def registered_webhook_url(self) -> str:
        """
        The webhook URL registered with Telegram. It ends with a hash of the secret, so that changing the secret
        registers the webhook again (Telegram does not tell which secret it uses).
        """
        version = hashlib.sha256(self._config.webhook_secret.encode()).hexdigest()[:12]
        return f"{self._config.webhook_url}?v={version}"

    def router(self) -> APIRouter:
        router = APIRouter(tags=["Channels"])

        @router.post(
            path=WEBHOOK_PATH,
            status_code=HTTPStatus.OK,
            responses={HTTPStatus.FORBIDDEN: {"description": f"Missing or wrong {SECRET_TOKEN_HEADER} header."}},
            name="telegram webhook",
            description="Called by Telegram with the updates of the Compass bot. Answers at once and handles the "
                        f"update in the background. Telegram authenticates with the {SECRET_TOKEN_HEADER} header.")
        async def _webhook(request: Request,
                           secret_token: Optional[str] = Header(default=None, alias=SECRET_TOKEN_HEADER),
                           service: IChannelGatewayService = Depends(get_channel_gateway_service),
                           channel_state: IChannelStateRepository = Depends(get_channel_state_repository)
                           ) -> Response:
            if secret_token is None or not hmac.compare_digest(secret_token.encode(),
                                                               self._config.webhook_secret.encode()):
                raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Forbidden")
            await self.receive_update(await request.body(), service, channel_state)
            return Response(status_code=HTTPStatus.OK)

        return router

    async def receive_update(self, body: bytes, service: IChannelGatewayService,
                             channel_state: IChannelStateRepository) -> None:
        """
        Start handling an update in the background, unless it was already received.

        :raises Exception: if the update cannot be recorded, so that Telegram sends it again later
        """
        set_channel_context(self.channel, ChannelOperation.WEBHOOK)
        try:
            update = Update.de_json(json.loads(body), self._bot)
        except Exception as e:  # pylint: disable=broad-except
            # sending it again would not help: answer OK so that Telegram drops it
            self._logger.error("Ignored an update that is not valid: %r", e)
            return
        if not isinstance(update, Update):
            return

        if not await channel_state.record_received_update(self.channel, update.update_id):
            self._logger.info("Ignored the update %s, received before", update.update_id)
            return
        self._background_tasks.run(self._handle_update(update, service), name=f"telegram-update-{update.update_id}")

    async def _handle_update(self, update: Update, service: IChannelGatewayService) -> None:
        event = to_incoming_event(update)
        if event is not None:
            await self.handle(event, service)

    async def start(self, metrics_service: IMetricsService) -> None:
        # Register in the background: the backend must not wait for Telegram to start, nor fail if it is unreachable.
        self._background_tasks.run(self._initialize(metrics_service), name="telegram-register")

    async def _initialize(self, metrics_service: IMetricsService) -> None:
        with sentry_sdk.isolation_scope():
            set_channel_context(self.channel, ChannelOperation.BOT_REGISTRATION)
            status = await self._register()
            await metrics_service.record_event(BotInitializedEvent(channel=self.channel,
                                                                   registration_status=status))

    async def stop(self) -> None:
        await self._background_tasks.wait(SHUTDOWN_TIMEOUT_SECONDS)
        try:
            await self._bot.shutdown()
        except TelegramError as e:
            self._logger.warning("Could not shut down the Telegram bot: %r", e)

    async def _register(self) -> BotRegistrationStatus:
        """
        Register the webhook and the command menu with Telegram, if they changed.

        Setting the webhook also stops any getUpdates polling of the token: Telegram sends the updates of a bot to one
        place only, so this deployment must be the only one that runs with the token (see docs/channels).
        """
        status = BotRegistrationStatus.UNCHANGED
        try:
            await self._bot.initialize()

            webhook_info = await self._bot.get_webhook_info()
            if webhook_info.url != self.registered_webhook_url:
                if webhook_info.url:
                    # another deployment (or an older secret) had the webhook: it no longer gets the updates
                    self._logger.warning("Replaced the Telegram webhook of another URL: %s", webhook_info.url)
                await self._bot.set_webhook(url=self.registered_webhook_url,
                                            secret_token=self._config.webhook_secret,
                                            allowed_updates=ALLOWED_UPDATES)
                self._logger.info("Registered the Telegram webhook %s", self._config.webhook_url)
                status = BotRegistrationStatus.REGISTERED

            if list(await self._bot.get_my_commands()) != COMMANDS:
                await self._bot.set_my_commands(COMMANDS)
                self._logger.info("Registered the Telegram command menu")
                status = BotRegistrationStatus.REGISTERED
            return status
        except TelegramError as e:
            capture_gateway_error(e)
            self._logger.error("Could not register the Telegram bot: %r", e)
            return BotRegistrationStatus.FAILED

    async def send_text(self, user_id: str, text: str, choices: Optional[list[str]]) -> None:
        # plain text, no parse mode: the texts of Compass are not escaped for Telegram markup
        await self._bot.send_message(chat_id=int(user_id), text=text, reply_markup=build_reply_markup(choices))

    async def send_document(self, user_id: str, file_name: str, content: bytes) -> None:
        # uploaded rather than sent by URL: Telegram fetches only PDF, GIF and ZIP files from a URL
        await self._bot.send_document(chat_id=int(user_id), document=InputFile(content, filename=file_name),
                                      write_timeout=60)

    async def send_typing(self, user_id: str) -> None:
        await self._bot.send_chat_action(chat_id=int(user_id), action=ChatAction.TYPING)
