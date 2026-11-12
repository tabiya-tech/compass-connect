import asyncio
from typing import Optional
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter

from app.channels.bots.bot import ChannelBot
from app.channels.bots.events import EventKind, IncomingEvent
from app.channels.service import ChannelUserNotFoundError, IChannelGatewayService
from app.channels.types import Channel, Document, IncomingMessage, OutgoingMessage
from app.i18n.translation_service import t
from app.i18n.types import Locale

USER_ID = "42"


class FakeChannelBot(ChannelBot):
    """
    A channel that records what it sends, to test the flow every channel shares.
    """

    def __init__(self, *, max_text_length: int = 4096, max_document_bytes: Optional[int] = None,
                 document_downloader=None):
        super().__init__(default_locale=Locale.EN_US, typing_interval_seconds=0.01,
                         document_downloader=document_downloader or AsyncMock(return_value=b"%PDF"))
        self._max_text_length = max_text_length
        self._max_document_bytes = max_document_bytes
        self.sent: list[tuple] = []
        self.typing_count = 0

    @property
    def channel(self) -> Channel:
        return Channel.TELEGRAM

    @property
    def max_text_length(self) -> int:
        return self._max_text_length

    @property
    def max_document_bytes(self) -> Optional[int]:
        return self._max_document_bytes

    def router(self) -> APIRouter:
        return APIRouter()

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_text(self, user_id: str, text: str, choices: Optional[list[str]]) -> None:
        self.sent.append(("text", user_id, text, choices))

    async def send_document(self, user_id: str, file_name: str, content: bytes) -> None:
        self.sent.append(("document", user_id, file_name, content))

    async def send_typing(self, user_id: str) -> None:
        self.typing_count += 1


@pytest.fixture
def service() -> AsyncMock:
    return AsyncMock(spec=IChannelGatewayService)


@pytest.fixture
def bot() -> FakeChannelBot:
    return FakeChannelBot()


def _text(key: str, **kwargs) -> tuple:
    return "text", USER_ID, t("messages", key, **kwargs), None


class TestHandle:
    @pytest.mark.asyncio
    async def test_starts_the_conversation_of_a_new_user(self, bot: FakeChannelBot, service: AsyncMock):
        # GIVEN a user with no conversation yet
        service.handle_sent_message.side_effect = ChannelUserNotFoundError()
        # AND the service returns the welcome message when the conversation is created
        service.initialize_conversation.return_value = [OutgoingMessage(text="Welcome!", choices=["Let's go"])]

        # WHEN the user opens the bot
        await bot.handle(IncomingEvent(kind=EventKind.COMMAND, user_id=USER_ID, text="/start"), service)

        # THEN their conversation is created
        service.initialize_conversation.assert_awaited_once_with(Channel.TELEGRAM, USER_ID)
        # AND the welcome message is sent with its choices
        assert bot.sent == [("text", USER_ID, "Welcome!", ["Let's go"])]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_event, expected_message", [
        pytest.param(IncomingEvent(kind=EventKind.TEXT, user_id=USER_ID, text="I sold vegetables"),
                     IncomingMessage(channel=Channel.TELEGRAM, channel_user_id=USER_ID, text="I sold vegetables"),
                     id="typed text or a tapped choice is sent as text"),
        pytest.param(IncomingEvent(kind=EventKind.COMMAND, user_id=USER_ID, text="/restart"),
                     IncomingMessage(channel=Channel.TELEGRAM, channel_user_id=USER_ID, command="/restart"),
                     id="a command is sent as a command"),
    ])
    async def test_sends_the_message_to_the_service(self, bot: FakeChannelBot, service: AsyncMock, given_event,
                                                    expected_message):
        # GIVEN the service replies with two messages, the second without choices
        service.handle_sent_message.return_value = [OutgoingMessage(text="First", choices=["A", "B"]),
                                                    OutgoingMessage(text="Second")]

        # WHEN the user sends the event
        await bot.handle(given_event, service)

        # THEN the message is sent to the service
        service.handle_sent_message.assert_awaited_once_with(expected_message)
        # AND the replies are sent in order, the second removing the buttons of the first
        assert bot.sent == [("text", USER_ID, "First", ["A", "B"]), ("text", USER_ID, "Second", [])]

    @pytest.mark.asyncio
    async def test_splits_a_long_reply_and_shows_the_choices_with_the_last_part(self, service: AsyncMock):
        # GIVEN a channel that sends at most 10 characters
        bot = FakeChannelBot(max_text_length=10)
        # AND the service replies with a long text with choices
        service.handle_sent_message.return_value = [OutgoingMessage(text="aaaa bbbb cccc dddd", choices=["Yes"])]

        # WHEN the user sends a message
        await bot.handle(IncomingEvent(kind=EventKind.TEXT, user_id=USER_ID, text="Hi"), service)

        # THEN the reply is split, and only the last part has the choices
        assert bot.sent == [("text", USER_ID, "aaaa bbbb", None), ("text", USER_ID, "cccc dddd", ["Yes"])]

    @pytest.mark.asyncio
    async def test_sends_a_document(self, service: AsyncMock):
        # GIVEN the service replies with the report
        given_downloader = AsyncMock(return_value=b"%PDF")
        bot = FakeChannelBot(document_downloader=given_downloader)
        given_document = Document(file_name="report.pdf", content_type="application/pdf",
                                  url="https://compass.test/report.pdf")
        service.handle_sent_message.return_value = [OutgoingMessage(text="Here is your report",
                                                                    document=given_document)]

        # WHEN the user asks for the report
        await bot.handle(IncomingEvent(kind=EventKind.COMMAND, user_id=USER_ID, text="/report"), service)

        # THEN the text is sent, then the document
        given_downloader.assert_awaited_once_with(given_document)
        assert bot.sent == [("text", USER_ID, "Here is your report", []),
                            ("document", USER_ID, "report.pdf", b"%PDF")]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("max_document_bytes, download_error", [
        pytest.param(None, RuntimeError("download failed"), id="the download fails"),
        pytest.param(3, None, id="the document is too large for the channel"),
    ])
    async def test_tells_the_user_when_the_document_cannot_be_sent(self, service: AsyncMock, max_document_bytes,
                                                                   download_error):
        # GIVEN the service replies with a document that cannot be sent
        bot = FakeChannelBot(max_document_bytes=max_document_bytes,
                             document_downloader=AsyncMock(return_value=b"%PDF", side_effect=download_error))
        service.handle_sent_message.return_value = [OutgoingMessage(text="Report", document=Document(
            file_name="report.pdf", content_type="application/pdf", url="https://compass.test/report.pdf"))]

        # WHEN the user asks for the report
        await bot.handle(IncomingEvent(kind=EventKind.COMMAND, user_id=USER_ID, text="/report"), service)

        # THEN the user is told the file could not be sent
        assert bot.sent == [("text", USER_ID, "Report", []), _text("channels.documentUnavailable")]

    @pytest.mark.asyncio
    async def test_tells_the_user_when_the_service_fails(self, bot: FakeChannelBot, service: AsyncMock):
        # GIVEN the service fails
        service.handle_sent_message.side_effect = RuntimeError("database down")

        # WHEN the user sends a message
        await bot.handle(IncomingEvent(kind=EventKind.TEXT, user_id=USER_ID, text="Hi"), service)

        # THEN the user is told something went wrong
        assert bot.sent == [_text("channels.unexpectedError")]

    @pytest.mark.asyncio
    async def test_rejects_a_text_that_is_too_long(self, bot: FakeChannelBot, service: AsyncMock):
        # WHEN the user sends a text longer than a conversation accepts
        await bot.handle(IncomingEvent(kind=EventKind.TEXT, user_id=USER_ID, text="x" * 1001), service)

        # THEN they are asked to shorten it, and the service is not called
        assert bot.sent == [_text("channels.messageTooLong", max_length=1000)]
        service.handle_sent_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_unsupported_message(self, bot: FakeChannelBot, service: AsyncMock):
        # WHEN the user sends e.g. a photo
        await bot.handle(IncomingEvent(kind=EventKind.UNSUPPORTED, user_id=USER_ID), service)

        # THEN they are asked to type, and the service is not called
        assert bot.sent == [_text("channels.unsupportedMessage")]
        service.handle_sent_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_shows_typing_while_the_turn_runs(self, bot: FakeChannelBot, service: AsyncMock):
        # GIVEN a turn that takes a while
        async def slow_reply(_message):
            await asyncio.sleep(0.05)
            return [OutgoingMessage(text="Done")]

        service.handle_sent_message.side_effect = slow_reply

        # WHEN the user sends a message
        await bot.handle(IncomingEvent(kind=EventKind.TEXT, user_id=USER_ID, text="Hi"), service)

        # THEN typing was shown more than once while waiting
        assert bot.typing_count > 1
        # AND stops once the reply is sent
        count_after_reply = bot.typing_count
        await asyncio.sleep(0.03)
        assert bot.typing_count == count_after_reply

    @pytest.mark.asyncio
    async def test_sends_the_replies_of_a_user_in_order(self, bot: FakeChannelBot, service: AsyncMock):
        # GIVEN the first message of the user takes longer than the second
        async def reply(message: IncomingMessage):
            await asyncio.sleep(0.05 if message.text == "first" else 0)
            return [OutgoingMessage(text=f"re: {message.text}")]

        service.handle_sent_message.side_effect = reply

        # WHEN the user sends two messages at once
        await asyncio.gather(bot.handle(IncomingEvent(kind=EventKind.TEXT, user_id=USER_ID, text="first"), service),
                             bot.handle(IncomingEvent(kind=EventKind.TEXT, user_id=USER_ID, text="second"), service))

        # THEN the replies come in the order of the messages
        assert [sent[2] for sent in bot.sent] == ["re: first", "re: second"]

    @pytest.mark.asyncio
    async def test_does_not_wait_for_other_users(self, bot: FakeChannelBot, service: AsyncMock):
        # GIVEN the turn of a first user is slow
        async def reply(message: IncomingMessage):
            await asyncio.sleep(0.05 if message.channel_user_id == "100" else 0)
            return [OutgoingMessage(text=message.channel_user_id)]

        service.handle_sent_message.side_effect = reply

        # WHEN two users send a message at once
        await asyncio.gather(bot.handle(IncomingEvent(kind=EventKind.TEXT, user_id="100", text="Hi"), service),
                             bot.handle(IncomingEvent(kind=EventKind.TEXT, user_id="200", text="Hi"), service))

        # THEN the second user gets their reply first
        assert [sent[2] for sent in bot.sent] == ["200", "100"]
