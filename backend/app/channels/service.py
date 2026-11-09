"""
The channels API: chat bots (Telegram, WhatsApp) bring their users to Compass. Each bot user gets an anonymous
Compass user, found by their channel and their id on the channel.
"""

import asyncio
import logging
import uuid
import weakref
from abc import ABC, abstractmethod

from app.agent.welcome_agent import WelcomeAgent
from app.channels.bws_renderer import BwsRenderer, is_letter
from app.channels.renderer import ConversationRenderer, TextRenderer
from app.channels.repository import IChannelStateRepository, PendingBwsAnswer
from app.channels.types import Channel, IncomingMessage, OutgoingMessage
from app.context_vars import client_id_ctx_var, session_id_ctx_var, user_id_ctx_var, user_language_ctx_var, \
    user_profile_context_var
from app.conversations.constants import MAX_MESSAGE_LENGTH
from app.conversations.service import ConversationAlreadyConcludedError, IConversationService
from app.conversations.types import ConversationMessageType
from app.i18n.translation_service import t
from app.i18n.types import Locale
from app.observability.treatment_group import set_treatment_group
from app.users.generate_session_id import generate_new_session_id
from app.users.plain_personal_data.service import IPlainPersonalDataService, format_plain_personal_data_for_prompt
from app.users.preferences_service import IUserPreferencesService
from app.users.repositories import IUserPreferenceRepository, UserPreferenceRepositoryError
from app.users.sensitive_personal_data.types import SensitivePersonalDataRequirement
from app.users.types import UserPreferences, UserPreferencesRepositoryUpdateRequest
from common_libs.time_utilities import get_now


class ChannelUserNotFoundError(Exception):
    """
    No Compass user for this channel user: the bot must initialize the conversation first.
    """


def get_channel_client_id(channel: Channel) -> str:
    """
    The client id of the users of a channel. The same for every user of the channel: the bot is their only client.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"compass:channel:{channel.value}"))


def generate_channel_user_id() -> str:
    """
    A new id for an anonymous Compass user created through a channel. Bot users have no Firebase account.
    """
    return uuid.uuid4().hex


class Command:
    START = "/start"
    RESTART = "/restart"
    REPORT = "/report"
    HELP = "/help"


def normalize_command(command: str) -> str:
    """
    The command without its arguments and the bot name Telegram adds in groups, e.g. "/Start@CompassBot now" is
    "/start".
    """
    parts = command.strip().split()
    if not parts:
        return ""
    return parts[0].split("@", 1)[0].lower()


class IChannelGatewayService(ABC):
    """
    Interface for the Channel Gateway Service

    Allows to mock the service in tests.
    """

    @abstractmethod
    async def initialize_conversation(self, channel: Channel, channel_user_id: str) -> list[OutgoingMessage]:
        """
        Find or create the anonymous Compass user of the channel user, with their preferences and a session. For now
        the user accepts the terms by starting the bot: accepted_tc is set to now if it is not set yet.

        :return: the welcome message, the same first message as in the web app
        :raises UserPreferenceRepositoryError: if the user preferences cannot be read or written
        """
        raise NotImplementedError()

    @abstractmethod
    async def handle_sent_message(self, message: IncomingMessage) -> list[OutgoingMessage]:
        """
        Handle a message (text or command) the user sent on the channel. The text is sent to the conversation of the
        active session. The messages of a user are handled one at a time, in the order they arrive.

        Commands:
        - /start: start the conversation, or tell the user to continue it
        - /restart: start a new conversation, in a new session
        - /report: send the skills report (not available yet)
        - /help, or any other command: the help text

        An error of the conversation (e.g. the conversation is already concluded) is a message to the user.

        :return: the messages to send to the user
        :raises ChannelUserNotFoundError: if the conversation of the channel user was not initialized
        :raises UserPreferenceRepositoryError: if the user preferences cannot be read
        """
        raise NotImplementedError()


class ChannelGatewayService(IChannelGatewayService):
    _user_locks: "weakref.WeakValueDictionary[str, asyncio.Lock]" = weakref.WeakValueDictionary()
    """
    One lock per user, so that the turns of a user do not overwrite each other's conversation state. Only within this
    process: two instances of the backend can still handle two messages of the same user at the same time.
    """

    def __init__(self, *,
                 user_preferences_repository: IUserPreferenceRepository,
                 user_preferences_service: IUserPreferencesService,
                 conversation_service: IConversationService,
                 plain_personal_data_service: IPlainPersonalDataService,
                 channel_state_repository: IChannelStateRepository,
                 default_language: str):
        self._user_preferences = user_preferences_repository
        self._user_preferences_service = user_preferences_service
        self._conversation_service = conversation_service
        self._plain_personal_data_service = plain_personal_data_service
        self._channel_state = channel_state_repository
        self._default_language = default_language
        self._bws_renderer = BwsRenderer()
        self._renderer = ConversationRenderer({ConversationMessageType.TEXT: TextRenderer(),
                                               ConversationMessageType.BWS_TASK: self._bws_renderer})
        # never log the channel user id: it is personal data (e.g. a phone number), log the Compass user id instead
        self._logger = logging.getLogger(self.__class__.__name__)

    async def initialize_conversation(self, channel: Channel, channel_user_id: str) -> list[OutgoingMessage]:
        user_id, preferences = await self._get_or_create_user(channel, channel_user_id)
        preferences = await self._set_context(user_id, preferences)

        # TODO: let the user accept the terms in the chat instead of accepting them for the user.
        if preferences.accepted_tc is None:
            await self._user_preferences.update_user_preference(
                user_id, UserPreferencesRepositoryUpdateRequest(accepted_tc=get_now()))

        # the same first message as the web app's conversation, in the language of the user
        return [OutgoingMessage(text=WelcomeAgent.get_first_encounter_message(user_language_ctx_var.get().value))]

    async def handle_sent_message(self, message: IncomingMessage) -> list[OutgoingMessage]:
        found = await self._user_preferences.get_user_preference_by_channel_user_id(message.channel,
                                                                                    message.channel_user_id)
        if found is None:
            raise ChannelUserNotFoundError()
        user_id, _ = found

        async with self._get_user_lock(user_id):
            try:
                # read the preferences again: the previous message of the user may have started a new session
                preferences = await self._user_preferences.get_user_preference_by_user_id(user_id)
                preferences = await self._set_context(user_id, preferences)
                await self._set_turn_context(user_id, preferences)
                session_id = preferences.sessions[0]

                if message.command:
                    return await self._handle_command(user_id, session_id, normalize_command(message.command))
                return await self._handle_text(user_id, session_id, message.text or "")
            except ConversationAlreadyConcludedError:
                self._logger.info("The user %s sent a message on a concluded conversation", user_id)
                return [OutgoingMessage(text=t("messages", "channels.conversationConcluded"))]
            except Exception as e:  # pylint: disable=broad-except
                self._logger.exception("Failed to handle the message of the user %s: %s", user_id, e)
                return [OutgoingMessage(text=t("messages", "channels.unexpectedError"))]

    async def _handle_command(self, user_id: str, session_id: int, command: str) -> list[OutgoingMessage]:
        if command == Command.START:
            if await self._is_new_conversation(user_id, session_id):
                return await self._send(user_id, session_id, "")
            return [OutgoingMessage(text=t("messages", "channels.welcomeBack"))]
        if command == Command.RESTART:
            session_id = await self._start_new_session(user_id)
            return await self._send(user_id, session_id, "")
        if command == Command.REPORT:
            # TODO: send the skills report as a document
            return [OutgoingMessage(text=t("messages", "channels.reportNotAvailable"))]
        return [OutgoingMessage(text=t("messages", "channels.help"))]

    async def _handle_text(self, user_id: str, session_id: int, text: str) -> list[OutgoingMessage]:
        if not text.strip():
            return [OutgoingMessage(text=t("messages", "channels.emptyMessage"))]
        if len(text) > MAX_MESSAGE_LENGTH:
            return [OutgoingMessage(text=t("messages", "channels.messageTooLong", max_length=MAX_MESSAGE_LENGTH))]

        if await self._is_new_conversation(user_id, session_id):
            # The welcome message was sent when the conversation was initialized, but not through a turn. Like the web
            # app, run the first turn with no input, so that the text of the user answers the welcome message.
            await self._conversation_service.send(user_id, session_id, "", clear_memory=False, filter_pii=False)

        pending = await self._channel_state.get_pending_bws_answer(session_id)
        if pending is not None:
            letter = pending.task.parse_letter(text)
            if letter is None:
                if is_letter(text):
                    # a letter that is not an option: ask again
                    return [self._bws_renderer.render_prompt(pending.task, pending.best_letter)]
                # otherwise the user answered in their own words (e.g. "most B, least D"), which Compass understands
            elif pending.best_letter is None or letter == pending.best_letter:
                # the most liked option, or the same option again as the least liked one: ask for the least liked one
                pending.best_letter = letter
                await self._channel_state.save_pending_bws_answer(pending)
                return [self._bws_renderer.render_prompt(pending.task, letter)]
            else:
                text = pending.task.build_answer(pending.best_letter, letter)

        return await self._send(user_id, session_id, text)

    async def _send(self, user_id: str, session_id: int, user_input: str) -> list[OutgoingMessage]:
        """
        Run a conversation turn, remember the BWS task it asks the user to answer if any, and render it.
        """
        response = await self._conversation_service.send(user_id, session_id, user_input, clear_memory=False,
                                                         filter_pii=False)
        open_task = self._bws_renderer.get_open_task(response)
        if open_task is not None:
            await self._channel_state.save_pending_bws_answer(PendingBwsAnswer(session_id=session_id, task=open_task))
        else:
            await self._channel_state.delete_pending_bws_answer(session_id)
        return self._renderer.render(response)

    async def _is_new_conversation(self, user_id: str, session_id: int) -> bool:
        history = await self._conversation_service.get_history_by_session_id(user_id, session_id)
        return not history.messages

    async def _start_new_session(self, user_id: str) -> int:
        """
        Start a new session, the active one from now on, like the web app does (see app/users/sessions.py).
        """
        preferences = await self._user_preferences.get_user_preference_by_user_id(user_id)
        new_session_id = generate_new_session_id()
        await self._user_preferences.update_user_preference(
            user_id, UserPreferencesRepositoryUpdateRequest(sessions=[new_session_id, *preferences.sessions]))
        session_id_ctx_var.set(new_session_id)
        self._logger.info("Started the session %s for the user %s", new_session_id, user_id)
        return new_session_id

    async def _set_turn_context(self, user_id: str, preferences: UserPreferences) -> None:
        """
        Set the rest of the context the web app sets for a conversation turn (see app/conversations/routes.py).
        """
        set_treatment_group(preferences.experiments)
        plain_personal_data = await self._plain_personal_data_service.get(user_id)
        if plain_personal_data:
            user_profile_context_var.set(format_plain_personal_data_for_prompt(plain_personal_data))

    @classmethod
    def _get_user_lock(cls, user_id: str) -> asyncio.Lock:
        lock = cls._user_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            cls._user_locks[user_id] = lock
        return lock

    async def _get_or_create_user(self, channel: Channel, channel_user_id: str) -> tuple[str, UserPreferences]:
        found = await self._user_preferences.get_user_preference_by_channel_user_id(channel, channel_user_id)
        if found is not None:
            return found

        user_id = generate_channel_user_id()
        try:
            # anonymous, without an invitation code
            preferences = await self._user_preferences_service.create_new_user_preferences(
                user_id=user_id,
                language=self._default_language,
                invitation_code=None,
                client_id=get_channel_client_id(channel),
                sensitive_personal_data_requirement=SensitivePersonalDataRequirement.NOT_AVAILABLE,
                channel=channel,
                channel_user_id=channel_user_id,
            )
            self._logger.info("Created the user %s for a %s user", user_id, channel.value)
            return user_id, preferences
        except UserPreferenceRepositoryError:
            # a concurrent request for the same channel user created it first
            found = await self._user_preferences.get_user_preference_by_channel_user_id(channel, channel_user_id)
            if found is None:
                raise
            return found

    async def _set_context(self, user_id: str, preferences: UserPreferences) -> UserPreferences:
        """
        Make sure the user has an active session (the first one), and set the context of the request: the ids for the
        logs and the language of the messages.
        """
        if not preferences.sessions:
            preferences = await self._user_preferences.update_user_preference(
                user_id, UserPreferencesRepositoryUpdateRequest(sessions=[generate_new_session_id()]))

        user_id_ctx_var.set(user_id)
        session_id_ctx_var.set(preferences.sessions[0])
        client_id_ctx_var.set(preferences.client_id)
        user_language_ctx_var.set(self._get_locale(preferences.language))
        return preferences

    def _get_locale(self, language: str | None) -> Locale:
        for candidate in (language, self._default_language):
            try:
                return Locale.from_locale_str(candidate)
            except ValueError:
                continue
        return Locale.EN_US
