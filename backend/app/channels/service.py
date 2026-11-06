"""
The channels API: chat bots (Telegram, WhatsApp) bring their users to Compass. Each bot user gets an anonymous
Compass user, found by their channel and their id on the channel.
"""

import logging
import uuid
from abc import ABC, abstractmethod

from app.agent.welcome_agent import WelcomeAgent
from app.channels.types import Channel, IncomingMessage, OutgoingMessage
from app.context_vars import client_id_ctx_var, session_id_ctx_var, user_id_ctx_var, user_language_ctx_var
from app.i18n.types import Locale
from app.users.generate_session_id import generate_new_session_id
from app.users.preferences_service import IUserPreferencesService
from app.users.repositories import IUserPreferenceRepository, UserPreferenceRepositoryError
from app.users.sensitive_personal_data.types import SensitivePersonalDataRequirement
from app.users.types import UserPreferences, UserPreferencesRepositoryUpdateRequest
from common_libs.time_utilities import get_now

HELLO_WORLD_MESSAGE = "Hello world"
"""
The reply to every message, until the messages are sent to the conversation.
"""


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
        Handle a message (text or command) the user sent on the channel.

        :return: the messages to send to the user
        :raises ChannelUserNotFoundError: if the conversation of the channel user was not initialized
        :raises UserPreferenceRepositoryError: if the user preferences cannot be read or written
        """
        raise NotImplementedError()


class ChannelGatewayService(IChannelGatewayService):
    def __init__(self, *,
                 user_preferences_repository: IUserPreferenceRepository,
                 user_preferences_service: IUserPreferencesService,
                 default_language: str):
        self._user_preferences = user_preferences_repository
        self._user_preferences_service = user_preferences_service
        self._default_language = default_language
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
        user_id, preferences = found
        await self._set_context(user_id, preferences)

        # TODO: send the text to the conversation of the active session instead of the fixed reply.
        return [OutgoingMessage(text=HELLO_WORLD_MESSAGE)]

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
