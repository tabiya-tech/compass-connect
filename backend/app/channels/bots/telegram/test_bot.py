import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from telegram import Bot, ReplyKeyboardMarkup, WebhookInfo
from telegram.constants import ChatAction
from telegram.error import NetworkError

from app.channels.bots.tasks import BackgroundTasks
from app.channels.bots.telegram.bot import ALLOWED_UPDATES, SECRET_TOKEN_HEADER, TelegramBot, \
    get_channel_state_repository
from app.channels.bots.telegram.config import WEBHOOK_PATH, TelegramConfig
from app.channels.bots.telegram.mapping import COMMANDS
from app.channels.repository import IChannelStateRepository
from app.channels.routes import get_channel_gateway_service
from app.channels.service import ChannelUserNotFoundError, IChannelGatewayService
from app.channels.types import Channel, IncomingMessage, OutgoingMessage
from app.i18n.types import Locale

SECRET = "the-secret"  # nosec B105 # a test value
CONFIG = TelegramConfig(bot_token="123:abc", webhook_secret=SECRET,  # nosec B106 # a test value
                        webhook_url="https://compass.test/api/api/channels/telegram/webhook")


def _text_update_json(update_id: int, text: str) -> dict:
    return {"update_id": update_id,
            "message": {"message_id": 1, "date": int(datetime.now(timezone.utc).timestamp()), "text": text,
                        "chat": {"id": 42, "type": "private"},
                        "from": {"id": 42, "is_bot": False, "first_name": "Test"}}}


@pytest.fixture
def telegram_api() -> AsyncMock:
    return AsyncMock(spec=Bot)


@pytest.fixture
def background_tasks() -> BackgroundTasks:
    return BackgroundTasks()


@pytest.fixture
def bot(telegram_api: AsyncMock, background_tasks: BackgroundTasks) -> TelegramBot:
    return TelegramBot(config=CONFIG, default_locale=Locale.EN_US, bot=telegram_api,
                       background_tasks=background_tasks, typing_interval_seconds=0.01)


@pytest.fixture
def service() -> AsyncMock:
    return AsyncMock(spec=IChannelGatewayService)


@pytest.fixture
def channel_state() -> AsyncMock:
    channel_state = AsyncMock(spec=IChannelStateRepository)
    channel_state.record_received_update.return_value = True
    return channel_state


@pytest.fixture
def client(bot: TelegramBot, service: AsyncMock, channel_state: AsyncMock) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(bot.router())
    app.dependency_overrides[get_channel_gateway_service] = lambda: service
    app.dependency_overrides[get_channel_state_repository] = lambda: channel_state
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://compass.test")


async def _post_update(client: httpx.AsyncClient, update: dict, secret=SECRET) -> httpx.Response:
    headers = {SECRET_TOKEN_HEADER: secret} if secret is not None else {}
    return await client.post(WEBHOOK_PATH, content=json.dumps(update), headers=headers)


class TestWebhook:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_secret", [
        pytest.param(None, id="no secret"),
        pytest.param("wrong", id="wrong secret"),
    ])
    async def test_refuses_a_request_without_the_secret(self, client, service, channel_state, given_secret):
        # WHEN the webhook is called without the secret Telegram sends
        response = await _post_update(client, _text_update_json(1, "Hi"), secret=given_secret)

        # THEN it is refused, and the update is ignored
        assert response.status_code == 403
        channel_state.record_received_update.assert_not_called()
        service.handle_sent_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_answers_at_once_and_handles_the_update_in_the_background(self, client, telegram_api,
                                                                            service, channel_state,
                                                                            background_tasks):
        # GIVEN a turn that waits until the test lets it reply
        turn_may_end = asyncio.Event()

        async def slow_turn(_message):
            await turn_may_end.wait()
            return [OutgoingMessage(text="Which one?", choices=["A", "B"])]

        service.handle_sent_message.side_effect = slow_turn

        # WHEN Telegram sends a message of the user
        response = await _post_update(client, _text_update_json(7, "I sold vegetables"))

        # THEN the webhook answers 200 before the turn ends
        assert response.status_code == 200
        channel_state.record_received_update.assert_awaited_once_with(Channel.TELEGRAM, 7)
        assert background_tasks.running == 1
        telegram_api.send_message.assert_not_called()

        # WHEN the turn ends
        turn_may_end.set()
        await background_tasks.wait(1)

        # THEN the message went to the service as the text of the Telegram user
        service.handle_sent_message.assert_awaited_once_with(
            IncomingMessage(channel=Channel.TELEGRAM, channel_user_id="42", text="I sold vegetables"))
        # AND the reply is sent with the choices as buttons
        kwargs = telegram_api.send_message.await_args.kwargs
        assert kwargs["chat_id"] == 42
        assert kwargs["text"] == "Which one?"
        assert [[button.text for button in row] for row in kwargs["reply_markup"].keyboard] == [["A", "B"]]

    @pytest.mark.asyncio
    async def test_ignores_an_update_received_before(self, client, service, channel_state, background_tasks):
        # GIVEN Telegram sends an update again
        channel_state.record_received_update.return_value = False

        # WHEN it reaches the webhook
        response = await _post_update(client, _text_update_json(7, "Hi"))

        # THEN it is acknowledged but not handled again
        assert response.status_code == 200
        assert background_tasks.running == 0
        service.handle_sent_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_drops_an_invalid_update(self, client, channel_state, background_tasks):
        # WHEN the webhook receives a body that is not an update
        response = await client.post(WEBHOOK_PATH, content=b"not json", headers={SECRET_TOKEN_HEADER: SECRET})

        # THEN it is acknowledged (sending it again would not help) and ignored
        assert response.status_code == 200
        channel_state.record_received_update.assert_not_called()
        assert background_tasks.running == 0

    @pytest.mark.asyncio
    async def test_fails_when_the_update_cannot_be_recorded(self, client, channel_state, background_tasks):
        # GIVEN the database is down
        channel_state.record_received_update.side_effect = RuntimeError("database down")

        # WHEN an update reaches the webhook
        # THEN the webhook fails, so that Telegram sends the update again later
        with pytest.raises(RuntimeError):
            await _post_update(client, _text_update_json(7, "Hi"))
        assert background_tasks.running == 0

    @pytest.mark.asyncio
    async def test_start_creates_the_conversation_of_a_new_user(self, client, telegram_api, service,
                                                               background_tasks):
        # GIVEN a user with no conversation yet
        service.handle_sent_message.side_effect = ChannelUserNotFoundError()
        service.initialize_conversation.return_value = [OutgoingMessage(text="Welcome")]

        # WHEN the user sends /start
        await _post_update(client, _text_update_json(8, "/start"))
        await background_tasks.wait(1)

        # THEN their conversation is created, and the welcome message sent
        service.initialize_conversation.assert_awaited_once_with(Channel.TELEGRAM, "42")
        assert telegram_api.send_message.await_args.kwargs["text"] == "Welcome"


class TestRegistration:
    @pytest.mark.asyncio
    async def test_registers_the_webhook_and_the_commands_when_they_changed(self, bot, telegram_api,
                                                                           background_tasks):
        # GIVEN Telegram has another webhook and no commands
        telegram_api.get_webhook_info.return_value = WebhookInfo(url="https://old.test/hook",
                                                                 has_custom_certificate=False,
                                                                 pending_update_count=0)
        telegram_api.get_my_commands.return_value = ()

        # WHEN the bot starts
        await bot.start()
        await background_tasks.wait(1)

        # THEN the webhook is registered with the secret, for messages and taps only
        telegram_api.set_webhook.assert_awaited_once_with(url=bot.registered_webhook_url, secret_token=SECRET,
                                                          allowed_updates=ALLOWED_UPDATES)
        assert bot.registered_webhook_url.startswith(CONFIG.webhook_url + "?v=")
        # AND the command menu is registered
        telegram_api.set_my_commands.assert_awaited_once_with(COMMANDS)

    @pytest.mark.asyncio
    async def test_does_not_register_again_what_did_not_change(self, bot, telegram_api, background_tasks):
        # GIVEN Telegram already has the webhook and the commands
        telegram_api.get_webhook_info.return_value = WebhookInfo(url=bot.registered_webhook_url,
                                                                 has_custom_certificate=False,
                                                                 pending_update_count=0)
        telegram_api.get_my_commands.return_value = tuple(COMMANDS)

        # WHEN the bot starts
        await bot.start()
        await background_tasks.wait(1)

        # THEN nothing is registered again
        telegram_api.set_webhook.assert_not_called()
        telegram_api.set_my_commands.assert_not_called()

    def test_changing_the_secret_changes_the_registered_url(self, telegram_api):
        # GIVEN two bots with the same webhook and different secrets
        def _bot(secret: str) -> TelegramBot:
            return TelegramBot(config=TelegramConfig(bot_token="t", webhook_secret=secret,  # nosec B106 # a test value
                                                     webhook_url=CONFIG.webhook_url),
                               default_locale=Locale.EN_US, bot=telegram_api)

        # THEN they register different URLs, so a new secret is registered
        assert _bot("one").registered_webhook_url != _bot("two").registered_webhook_url
        # AND the secret is not in the URL
        assert "one" not in _bot("one").registered_webhook_url.split("?v=")[1]

    @pytest.mark.asyncio
    async def test_a_telegram_failure_does_not_fail_the_startup(self, bot, telegram_api, background_tasks):
        # GIVEN Telegram cannot be reached
        telegram_api.initialize.side_effect = NetworkError("unreachable")

        # WHEN the bot starts
        await bot.start()
        await background_tasks.wait(1)

        # THEN it does not fail, and nothing is registered
        telegram_api.set_webhook.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_waits_for_the_turns_and_shuts_down(self, bot, telegram_api, background_tasks):
        # GIVEN a turn in progress
        given_turn = AsyncMock()
        background_tasks.run(given_turn(), name="turn")

        # WHEN the bot stops
        await bot.stop()

        # THEN the turn ended, and the bot shut down
        given_turn.assert_awaited_once()
        assert background_tasks.running == 0
        telegram_api.shutdown.assert_awaited_once()


class TestSend:
    @pytest.mark.asyncio
    async def test_send_text_with_choices(self, bot, telegram_api):
        # WHEN a text with choices is sent
        await bot.send_text("42", "Pick one", ["A", "B"])

        # THEN it is sent as plain text to the chat of the user, with a keyboard of the choices
        kwargs = telegram_api.send_message.await_args.kwargs
        assert kwargs["chat_id"] == 42
        assert kwargs["text"] == "Pick one"
        assert "parse_mode" not in kwargs
        assert isinstance(kwargs["reply_markup"], ReplyKeyboardMarkup)

    @pytest.mark.asyncio
    async def test_send_document_uploads_the_file(self, bot, telegram_api):
        # WHEN a document is sent
        await bot.send_document("42", "report.docx", b"PK")

        # THEN the file is uploaded with its name
        kwargs = telegram_api.send_document.await_args.kwargs
        assert kwargs["chat_id"] == 42
        assert kwargs["document"].filename == "report.docx"
        assert kwargs["document"].input_file_content == b"PK"

    @pytest.mark.asyncio
    async def test_send_typing(self, bot, telegram_api):
        await bot.send_typing("42")
        telegram_api.send_chat_action.assert_awaited_once_with(chat_id=42, action=ChatAction.TYPING)

    def test_channel_limits(self, bot):
        assert bot.channel == Channel.TELEGRAM
        assert bot.max_text_length == 4096
        assert bot.max_document_bytes == 50 * 1024 * 1024
