import asyncio
import contextlib
import logging
import weakref
from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Optional, TypeVar

import httpx
import sentry_sdk
from fastapi import APIRouter

from app.channels.bots.events import EventKind, IncomingEvent
from app.channels.bots.text import split_text
from app.channels.observability import ChannelOperation, capture_gateway_error, set_channel_context
from app.channels.service import ChannelUserNotFoundError, IChannelGatewayService
from app.channels.types import Channel, Document, IncomingMessage, OutgoingMessage
from app.conversations.constants import MAX_MESSAGE_LENGTH
from app.i18n.translation_service import get_i18n_manager, t
from app.i18n.types import Locale
from app.metrics.services.service import IMetricsService

T = TypeVar("T")

DocumentDownloader = Callable[[Document], Awaitable[bytes]]


async def download_document(document: Document) -> bytes:
    """
    Download the content of a document, to upload it to the channel.
    """
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
        response = await client.get(document.url)
        response.raise_for_status()
        return response.content


class ChannelBot(ABC):
    """
    A chat bot that connects the users of one channel (e.g. Telegram) to their Compass conversation.

    It only translates between the channel and the channels service, which runs the conversation. This class holds the
    flow that is the same on every channel (`handle`). A channel subclasses it to receive its updates (`router`, e.g. a
    webhook), turn them into `IncomingEvent`s for `handle`, and implement the `send_*` methods.
    """

    def __init__(self, *,
                 default_locale: Locale,
                 typing_interval_seconds: float = 4.0,
                 document_downloader: DocumentDownloader = download_document):
        """
        :param default_locale: the language of the texts of the bot until the channels service knows the user's
        """
        self._default_locale = default_locale
        self._typing_interval_seconds = typing_interval_seconds
        self._download_document = document_downloader
        # One lock per user, so that the replies of a user are sent in the order of their messages. Weak, so that the
        # lock of a user goes away once nothing waits on it.
        self._user_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._logger = logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def channel(self) -> Channel:
        raise NotImplementedError()

    @property
    @abstractmethod
    def max_text_length(self) -> int:
        """ The longest text the channel can send in one message. """
        raise NotImplementedError()

    @property
    def max_document_bytes(self) -> Optional[int]:
        """ The largest file the channel can send, or None if there is no limit. """
        return None

    @abstractmethod
    def router(self) -> APIRouter:
        """ The routes the channel calls, e.g. its webhook. """
        raise NotImplementedError()

    @abstractmethod
    async def start(self, metrics_service: IMetricsService) -> None:
        """
        Called when the backend starts, e.g. to register the webhook. Must not fail the startup.

        :param metrics_service: to record that the bot initialized (BOT_INITIALIZED)
        """
        raise NotImplementedError()

    @abstractmethod
    async def stop(self) -> None:
        """ Called when the backend stops: finish the work in progress and release the resources. """
        raise NotImplementedError()

    @abstractmethod
    async def send_text(self, user_id: str, text: str, choices: Optional[list[str]]) -> None:
        """
        Send a text to the user.

        :param choices: The buttons to show. An empty list removes the buttons shown before. None leaves them as they
            are (e.g. for the first parts of a long text).
        """
        raise NotImplementedError()

    @abstractmethod
    async def send_document(self, user_id: str, file_name: str, content: bytes) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def send_typing(self, user_id: str) -> None:
        """ Show the user that the bot is preparing an answer. """
        raise NotImplementedError()

    async def handle(self, event: IncomingEvent, service: IChannelGatewayService) -> None:
        """
        Handle what the user did: pass it to the channels service, and send the user the messages it returns.

        Runs in its own Sentry isolation scope: it usually runs in the background, after the webhook answered, and its
        channel tags must not reach other work.
        """
        with sentry_sdk.isolation_scope():
            await self._handle(event, service)

    async def _handle(self, event: IncomingEvent, service: IChannelGatewayService) -> None:
        operation = ChannelOperation.COMMAND if event.kind == EventKind.COMMAND else \
            ChannelOperation.CONVERSATION_MESSAGE
        set_channel_context(self.channel, operation)

        # The texts of the bot are in the default language until the service sets the language of the user.
        get_i18n_manager().set_locale(self._default_locale)

        lock = self._user_locks.get(event.user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._user_locks[event.user_id] = lock

        async with lock:
            if event.kind == EventKind.UNSUPPORTED:
                await self.send_text(event.user_id, t("messages", "channels.unsupportedMessage"), None)
                return
            if event.kind == EventKind.TEXT and len(event.text or "") > MAX_MESSAGE_LENGTH:
                await self.send_text(event.user_id,
                                     t("messages", "channels.messageTooLong", max_length=MAX_MESSAGE_LENGTH), None)
                return

            try:
                messages = await self._while_typing(event.user_id, self._call_service(event, service))
            except Exception as e:  # pylint: disable=broad-except
                capture_gateway_error(e)
                self._logger.exception("Failed to handle a %s event: %s", event.kind.value, e)
                await self.send_text(event.user_id, t("messages", "channels.unexpectedError"), None)
                return

            try:
                await self._send_messages(event.user_id, messages)
            except Exception as e:
                # the channel did not take the reply (e.g. Telegram is down, or the user blocked the bot)
                capture_gateway_error(e)
                raise

    async def _call_service(self, event: IncomingEvent, service: IChannelGatewayService) -> list[OutgoingMessage]:
        if event.kind == EventKind.COMMAND:
            message = IncomingMessage(channel=self.channel, channel_user_id=event.user_id, command=event.text)
        else:
            message = IncomingMessage(channel=self.channel, channel_user_id=event.user_id, text=event.text)
        try:
            return await service.handle_sent_message(message)
        except ChannelUserNotFoundError:
            # The first message of the user (usually /start): create their conversation, and send its welcome message.
            return await service.initialize_conversation(self.channel, event.user_id)

    async def _send_messages(self, user_id: str, messages: list[OutgoingMessage]) -> None:
        for message in messages:
            chunks = split_text(message.text, self.max_text_length)
            for index, chunk in enumerate(chunks):
                is_last_chunk = index == len(chunks) - 1
                await self.send_text(user_id, chunk, message.choices if is_last_chunk else None)
            if message.document is not None:
                await self._send_document(user_id, message.document)

    async def _send_document(self, user_id: str, document: Document) -> None:
        try:
            content = await self._while_typing(user_id, self._download_document(document))
        except Exception as e:  # pylint: disable=broad-except
            self._logger.error("Could not download the document %s: %s", document.file_name, e)
            await self.send_text(user_id, t("messages", "channels.documentUnavailable"), None)
            return

        if self.max_document_bytes is not None and len(content) > self.max_document_bytes:
            self._logger.error("The document %s is too large for %s: %s bytes",
                               document.file_name, self.channel.value, len(content))
            await self.send_text(user_id, t("messages", "channels.documentUnavailable"), None)
            return
        await self.send_document(user_id, document.file_name, content)

    async def _while_typing(self, user_id: str, awaitable: Awaitable[T]) -> T:
        typing_task = asyncio.create_task(self._keep_typing(user_id))
        try:
            return await awaitable
        finally:
            typing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await typing_task

    async def _keep_typing(self, user_id: str) -> None:
        while True:
            try:
                await self.send_typing(user_id)
            except Exception as e:  # pylint: disable=broad-except
                # the indicator is best effort: the answer still comes
                self._logger.warning("Could not show the typing indicator: %r", e)
            await asyncio.sleep(self._typing_interval_seconds)
