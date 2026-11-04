import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable
from unittest.mock import AsyncMock

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.welcome_agent import WelcomeAgent
from app.channels.service import ChannelGatewayService, ChannelUserNotFoundError, HELLO_WORLD_MESSAGE, \
    get_channel_client_id
from app.channels.types import Channel, IncomingMessage
from app.metrics.services.service import IMetricsService
from app.metrics.types import UserAccountCreatedEvent
from app.server_dependencies.database_collections import Collections
from app.users.preferences_service import UserPreferencesService
from app.users.repositories import UserPreferenceRepository
from app.users.sensitive_personal_data.types import SensitivePersonalDataRequirement

_DEFAULT_LANGUAGE = "en-US"


@dataclass
class _Setup:
    service: ChannelGatewayService
    db: AsyncIOMotorDatabase
    user_preferences: UserPreferenceRepository
    metrics_service: AsyncMock


@pytest.fixture(scope="function")
async def setup(in_memory_application_database: Awaitable[AsyncIOMotorDatabase],
                setup_application_config) -> _Setup:
    # the metric events and the messages read the application config
    db = await in_memory_application_database
    user_preferences = UserPreferenceRepository(db)
    metrics_service = AsyncMock(spec=IMetricsService)
    service = ChannelGatewayService(
        user_preferences_repository=user_preferences,
        user_preferences_service=UserPreferencesService(user_preferences, metrics_service),
        default_language=_DEFAULT_LANGUAGE,
    )
    return _Setup(service, db, user_preferences, metrics_service)


def _message(channel_user_id: str, text: str | None = None, command: str | None = None,
             channel: Channel = Channel.TELEGRAM) -> IncomingMessage:
    return IncomingMessage(channel=channel, channel_user_id=channel_user_id, text=text, command=command)


async def _count_users(db: AsyncIOMotorDatabase, channel_user_id: str) -> int:
    return await db.get_collection(Collections.USER_PREFERENCES).count_documents({"channel_user_id": channel_user_id})


@pytest.mark.asyncio
class TestInitializeConversation:
    async def test_creates_an_anonymous_user_with_preferences_and_a_session(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user who never talked to Compass
        given_channel_user_id = "100200300"

        # WHEN the bot initializes their conversation
        await s.service.initialize_conversation(Channel.TELEGRAM, given_channel_user_id)

        # THEN a Compass user is linked to the Telegram user
        actual = await s.user_preferences.get_user_preference_by_channel_user_id(Channel.TELEGRAM,
                                                                                 given_channel_user_id)
        assert actual is not None
        actual_user_id, actual_preferences = actual
        assert actual_user_id
        assert actual_preferences.channel == Channel.TELEGRAM.value
        assert actual_preferences.channel_user_id == given_channel_user_id
        # AND the user is anonymous: no invitation code
        assert actual_preferences.invitation_code is None
        # AND the terms are accepted for the user
        assert actual_preferences.accepted_tc is not None
        assert actual_preferences.sensitive_personal_data_requirement == \
               SensitivePersonalDataRequirement.NOT_AVAILABLE.value
        # AND the user has the default language, the client id of the channel and one session
        assert actual_preferences.language == _DEFAULT_LANGUAGE
        assert actual_preferences.client_id == get_channel_client_id(Channel.TELEGRAM)
        assert len(actual_preferences.sessions) == 1
        # AND the account creation is recorded
        actual_event = s.metrics_service.record_event.await_args.args[0]
        assert isinstance(actual_event, UserAccountCreatedEvent)

    async def test_returns_only_the_welcome_message(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user who never talked to Compass

        # WHEN the bot initializes their conversation
        actual_messages = await s.service.initialize_conversation(Channel.TELEGRAM, "100200300")

        # THEN the bot gets only the welcome message of the web app, without choices
        assert len(actual_messages) == 1
        assert actual_messages[0].text == WelcomeAgent.get_first_encounter_message(_DEFAULT_LANGUAGE)
        assert actual_messages[0].choices == []

    async def test_repeat_calls_reuse_the_same_user_and_session(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation was initialized
        given_channel_user_id = "100200300"
        await s.service.initialize_conversation(Channel.TELEGRAM, given_channel_user_id)
        given_user_id, given_preferences = await s.user_preferences.get_user_preference_by_channel_user_id(
            Channel.TELEGRAM, given_channel_user_id)

        # WHEN the bot initializes their conversation again
        await s.service.initialize_conversation(Channel.TELEGRAM, given_channel_user_id)

        # THEN the same Compass user and session are used
        actual_user_id, actual_preferences = await s.user_preferences.get_user_preference_by_channel_user_id(
            Channel.TELEGRAM, given_channel_user_id)
        assert actual_user_id == given_user_id
        assert actual_preferences.sessions == given_preferences.sessions
        # AND the date the terms were accepted does not change
        assert actual_preferences.accepted_tc == given_preferences.accepted_tc
        # AND no other user is created
        assert await _count_users(s.db, given_channel_user_id) == 1

    async def test_concurrent_calls_create_one_user(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user who never talked to Compass
        given_channel_user_id = "100200300"

        # WHEN the bot initializes their conversation twice at the same time
        await asyncio.gather(s.service.initialize_conversation(Channel.TELEGRAM, given_channel_user_id),
                             s.service.initialize_conversation(Channel.TELEGRAM, given_channel_user_id))

        # THEN only one Compass user is created
        assert await _count_users(s.db, given_channel_user_id) == 1

    async def test_the_same_id_on_another_channel_is_another_user(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation was initialized
        given_channel_user_id = "100200300"
        await s.service.initialize_conversation(Channel.TELEGRAM, given_channel_user_id)

        # WHEN a WhatsApp user with the same id starts a conversation
        await s.service.initialize_conversation(Channel.WHATSAPP, given_channel_user_id)

        # THEN they get their own Compass user
        actual_telegram_user_id, _ = await s.user_preferences.get_user_preference_by_channel_user_id(
            Channel.TELEGRAM, given_channel_user_id)
        actual_whatsapp_user_id, _ = await s.user_preferences.get_user_preference_by_channel_user_id(
            Channel.WHATSAPP, given_channel_user_id)
        assert actual_telegram_user_id != actual_whatsapp_user_id

    async def test_accepts_the_terms_of_a_user_created_without_them(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose preferences have no accepted terms
        given_channel_user_id = "100200300"
        await s.service.initialize_conversation(Channel.TELEGRAM, given_channel_user_id)
        given_user_id, _ = await s.user_preferences.get_user_preference_by_channel_user_id(
            Channel.TELEGRAM, given_channel_user_id)
        await s.db.get_collection(Collections.USER_PREFERENCES).update_one({"user_id": given_user_id},
                                                                          {"$set": {"accepted_tc": None}})

        # WHEN the bot initializes their conversation again
        actual_messages = await s.service.initialize_conversation(Channel.TELEGRAM, given_channel_user_id)

        # THEN the terms are accepted for the user
        _, actual_preferences = await s.user_preferences.get_user_preference_by_channel_user_id(
            Channel.TELEGRAM, given_channel_user_id)
        assert actual_preferences.accepted_tc is not None
        # AND the bot gets only the welcome message
        assert len(actual_messages) == 1


@pytest.mark.asyncio
class TestHandleSentMessage:
    @pytest.mark.parametrize("given_text, given_command", [("Tell me about jobs", None), (None, "/report")])
    async def test_replies_hello_world(self, setup: Awaitable[_Setup], given_text: str | None,
                                       given_command: str | None):
        s = await setup
        # GIVEN a Telegram user whose conversation was initialized
        given_channel_user_id = "100200300"
        await s.service.initialize_conversation(Channel.TELEGRAM, given_channel_user_id)

        # WHEN the user sends a message or a command
        actual_messages = await s.service.handle_sent_message(
            _message(given_channel_user_id, text=given_text, command=given_command))

        # THEN the bot gets "Hello world"
        assert len(actual_messages) == 1
        assert actual_messages[0].text == HELLO_WORLD_MESSAGE
        assert actual_messages[0].choices == []

    async def test_unknown_channel_user_raises_not_found(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation was never initialized
        given_channel_user_id = "100200300"

        # WHEN the user sends a message
        # THEN the user is not found
        with pytest.raises(ChannelUserNotFoundError):
            await s.service.handle_sent_message(_message(given_channel_user_id, text="hi"))
        # AND no user is created
        assert await _count_users(s.db, given_channel_user_id) == 0


@pytest.mark.asyncio
async def test_channel_user_id_is_not_logged(setup: Awaitable[_Setup], caplog: pytest.LogCaptureFixture):
    s = await setup
    # GIVEN a Telegram user id
    given_channel_user_id = "987654321"

    # WHEN the bot initializes the conversation, twice at the same time, and the user sends messages
    # (the mongo driver logs its commands at DEBUG, filters included; only our own logs are checked)
    caplog.set_level(logging.INFO, logger="pymongo")
    with caplog.at_level(logging.DEBUG):
        await asyncio.gather(s.service.initialize_conversation(Channel.TELEGRAM, given_channel_user_id),
                             s.service.initialize_conversation(Channel.TELEGRAM, given_channel_user_id))
        await s.service.handle_sent_message(_message(given_channel_user_id, text="hi"))
        await s.service.handle_sent_message(_message(given_channel_user_id, command="/report"))

    # THEN the Telegram user id is in none of the logs
    assert given_channel_user_id not in caplog.text
