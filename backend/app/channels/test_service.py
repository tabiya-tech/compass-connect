import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable
from unittest.mock import AsyncMock

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.welcome_agent import WelcomeAgent
from app.channels.repository import ChannelStateRepository
from app.channels.service import ChannelGatewayService, ChannelUserNotFoundError, get_channel_client_id
from app.channels.types import Channel, IncomingMessage
from app.conversations.constants import MAX_MESSAGE_LENGTH
from app.conversations.service import ConversationAlreadyConcludedError, IConversationService
from app.i18n.translation_service import t
from app.conversations.types import ConversationMessage, ConversationMessageSender, ConversationMessageType, \
    ConversationPhaseResponse, ConversationResponse, CurrentConversationPhaseResponse, QuickReplyOption
from app.metrics.services.service import IMetricsService
from app.metrics.types import UserAccountCreatedEvent
from app.server_dependencies.database_collections import Collections
from app.users.preferences_service import UserPreferencesService
from app.users.plain_personal_data.service import IPlainPersonalDataService
from app.users.repositories import UserPreferenceRepository
from app.users.sensitive_personal_data.types import SensitivePersonalDataRequirement
from common_libs.time_utilities import get_now

_DEFAULT_LANGUAGE = "en-US"


@dataclass
class _Setup:
    service: ChannelGatewayService
    db: AsyncIOMotorDatabase
    user_preferences: UserPreferenceRepository
    metrics_service: AsyncMock
    conversation_service: AsyncMock


@pytest.fixture(scope="function")
async def setup(in_memory_application_database: Awaitable[AsyncIOMotorDatabase],
                setup_application_config) -> _Setup:
    # the metric events and the messages read the application config
    db = await in_memory_application_database
    user_preferences = UserPreferenceRepository(db)
    metrics_service = AsyncMock(spec=IMetricsService)
    # a conversation with no messages yet, that replies with a text message
    conversation_service = AsyncMock(spec=IConversationService)
    conversation_service.get_history_by_session_id.return_value = _response()
    conversation_service.send.return_value = _response(_compass_message("Compass reply"))
    plain_personal_data_service = AsyncMock(spec=IPlainPersonalDataService)
    plain_personal_data_service.get.return_value = None
    service = ChannelGatewayService(
        user_preferences_repository=user_preferences,
        user_preferences_service=UserPreferencesService(user_preferences, metrics_service),
        conversation_service=conversation_service,
        plain_personal_data_service=plain_personal_data_service,
        channel_state_repository=ChannelStateRepository(db),
        default_language=_DEFAULT_LANGUAGE,
    )
    return _Setup(service, db, user_preferences, metrics_service, conversation_service)


def _text(key: str, **kwargs) -> str:
    """ A text of the bot, in the language of the user (set by the service). """
    return t("messages", f"channels.{key}", **kwargs)


def _compass_message(text: str, **kwargs) -> ConversationMessage:
    return ConversationMessage(message_id="message-id", message=text, sent_at=get_now(),
                               sender=ConversationMessageSender.COMPASS, **kwargs)


def _bws_message(task_id: str = "0") -> ConversationMessage:
    return _compass_message("Question 1 of 8\nA. Analysing data\nB. Helping people\nC. Repairing machines",
                            message_type=ConversationMessageType.BWS_TASK,
                            metadata={"task_id": task_id, "task_number": int(task_id) + 1, "total_tasks": 8,
                                      "alternatives": [{"wa_id": "wa.a", "label": "Analysing data"},
                                                       {"wa_id": "wa.b", "label": "Helping people"},
                                                       {"wa_id": "wa.c", "label": "Repairing machines"}]})


def _response(*messages: ConversationMessage, completed: bool = False) -> ConversationResponse:
    return ConversationResponse(messages=list(messages), conversation_completed=completed,
                                current_phase=ConversationPhaseResponse(
                                    percentage=0, phase=CurrentConversationPhaseResponse.INTRO))


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


async def _initialize(s: _Setup, channel_user_id: str = "100200300") -> tuple[str, int]:
    """
    Initialize the conversation of a Telegram user, and start it with a first turn.

    :return: the Compass user id and the active session id
    """
    await s.service.initialize_conversation(Channel.TELEGRAM, channel_user_id)
    user_id, preferences = await s.user_preferences.get_user_preference_by_channel_user_id(Channel.TELEGRAM,
                                                                                           channel_user_id)
    return user_id, preferences.sessions[0]


def _started(s: _Setup):
    """ The conversation already has messages. """
    s.conversation_service.get_history_by_session_id.return_value = _response(_compass_message("Welcome"))


@pytest.mark.asyncio
class TestHandleSentMessage:
    async def test_sends_the_text_to_the_conversation_of_the_active_session(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation started
        given_user_id, given_session_id = await _initialize(s)
        _started(s)
        # AND Compass replies with a message and quick replies
        s.conversation_service.send.return_value = _response(
            _compass_message("Tell me more", quick_reply_options=[QuickReplyOption(label="Yes")]))

        # WHEN the user sends a text
        actual_messages = await s.service.handle_sent_message(_message("100200300", text="I sell vegetables"))

        # THEN the text is sent to the conversation of the active session
        s.conversation_service.send.assert_awaited_once_with(given_user_id, given_session_id, "I sell vegetables",
                                                             clear_memory=False, filter_pii=False)
        # AND the bot gets the reply of Compass with its quick replies as choices
        assert [(m.text, m.choices) for m in actual_messages] == [("Tell me more", ["Yes"])]

    async def test_first_text_runs_the_first_turn_before(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation was initialized, and has no messages yet
        given_user_id, given_session_id = await _initialize(s)

        # WHEN the user sends their first text
        actual_messages = await s.service.handle_sent_message(_message("100200300", text="Hi"))

        # THEN the first turn runs with no input, like in the web app, and then the text is sent
        assert [c.args for c in s.conversation_service.send.await_args_list] == [
            (given_user_id, given_session_id, ""), (given_user_id, given_session_id, "Hi")]
        # AND the bot gets only the reply to the text, the welcome message was already sent
        assert [m.text for m in actual_messages] == ["Compass reply"]

    async def test_too_long_text_is_not_sent(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation started
        await _initialize(s)
        _started(s)
        given_message = _message("100200300", text="hi")
        # AND a text longer than the maximum (the route rejects it already, the service checks it again)
        given_message.text = "a" * (MAX_MESSAGE_LENGTH + 1)

        # WHEN the user sends it
        actual_messages = await s.service.handle_sent_message(given_message)

        # THEN the text is not sent to the conversation
        s.conversation_service.send.assert_not_awaited()
        # AND the user is told it is too long
        assert [m.text for m in actual_messages] == [_text("messageTooLong", max_length=MAX_MESSAGE_LENGTH)]

    async def test_empty_text_is_not_sent(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation started
        await _initialize(s)
        _started(s)

        # WHEN the user sends a message with neither text nor command
        actual_messages = await s.service.handle_sent_message(_message("100200300"))

        # THEN nothing is sent to the conversation, and the user is told what to do
        s.conversation_service.send.assert_not_awaited()
        assert [m.text for m in actual_messages] == [_text("emptyMessage")]

    async def test_messages_of_a_user_are_handled_one_at_a_time(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation started
        await _initialize(s)
        _started(s)
        # AND a conversation turn that takes some time
        given_running = 0
        actual_max_running = 0

        async def _slow_send(*_args, **_kwargs):
            nonlocal given_running, actual_max_running
            given_running += 1
            actual_max_running = max(actual_max_running, given_running)
            await asyncio.sleep(0.05)
            given_running -= 1
            return _response(_compass_message("Compass reply"))

        s.conversation_service.send.side_effect = _slow_send

        # WHEN the user sends two messages at the same time
        await asyncio.gather(s.service.handle_sent_message(_message("100200300", text="one")),
                             s.service.handle_sent_message(_message("100200300", text="two")))

        # THEN the two turns ran one after the other
        assert s.conversation_service.send.await_count == 2
        assert actual_max_running == 1


@pytest.mark.asyncio
class TestCommands:
    async def test_start_runs_the_first_turn_of_a_new_conversation(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation has no messages yet
        given_user_id, given_session_id = await _initialize(s)
        # AND the first turn replies with the welcome message and quick replies
        s.conversation_service.send.return_value = _response(
            _compass_message("Welcome", quick_reply_options=[QuickReplyOption(label="Let's start")]))

        # WHEN the user sends /start
        actual_messages = await s.service.handle_sent_message(_message("100200300", command="/start"))

        # THEN the first turn runs with no input
        s.conversation_service.send.assert_awaited_once_with(given_user_id, given_session_id, "",
                                                             clear_memory=False, filter_pii=False)
        # AND the bot gets the welcome message with its choices
        assert [(m.text, m.choices) for m in actual_messages] == [("Welcome", ["Let's start"])]

    @pytest.mark.parametrize("given_command", ["/start", "/START", "/start@CompassBot"])
    async def test_start_resumes_a_started_conversation(self, setup: Awaitable[_Setup], given_command: str):
        s = await setup
        # GIVEN a Telegram user whose conversation started
        await _initialize(s)
        _started(s)

        # WHEN the user sends /start
        actual_messages = await s.service.handle_sent_message(_message("100200300", command=given_command))

        # THEN nothing is sent to the conversation
        s.conversation_service.send.assert_not_awaited()
        # AND the user is told to continue where they left off
        assert [m.text for m in actual_messages] == [_text("welcomeBack")]

    async def test_restart_starts_a_new_session(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation started
        given_user_id, given_session_id = await _initialize(s)
        _started(s)
        # AND the first turn of a conversation replies with the welcome message
        s.conversation_service.send.return_value = _response(_compass_message("Welcome"))

        # WHEN the user sends /restart
        actual_messages = await s.service.handle_sent_message(_message("100200300", command="/restart"))

        # THEN the user has a new active session, and keeps the previous one
        _, actual_preferences = await s.user_preferences.get_user_preference_by_channel_user_id(Channel.TELEGRAM,
                                                                                                "100200300")
        assert len(actual_preferences.sessions) == 2
        actual_session_id = actual_preferences.sessions[0]
        assert actual_preferences.sessions[1] == given_session_id
        # AND the first turn of the new session runs
        s.conversation_service.send.assert_awaited_once_with(given_user_id, actual_session_id, "",
                                                             clear_memory=False, filter_pii=False)
        assert [m.text for m in actual_messages] == ["Welcome"]

        # WHEN the user then sends a text
        s.conversation_service.send.reset_mock()
        await s.service.handle_sent_message(_message("100200300", text="Hi"))

        # THEN it is sent to the new session
        assert s.conversation_service.send.await_args.args[1] == actual_session_id

    async def test_report_is_not_available_yet(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation started
        await _initialize(s)
        _started(s)

        # WHEN the user sends /report
        actual_messages = await s.service.handle_sent_message(_message("100200300", command="/report"))

        # THEN the user is told the report is not available yet
        s.conversation_service.send.assert_not_awaited()
        assert [m.text for m in actual_messages] == [_text("reportNotAvailable")]
        assert actual_messages[0].document is None

    @pytest.mark.parametrize("given_command", ["/help", "/unknown"])
    async def test_help_and_unknown_commands_send_the_help(self, setup: Awaitable[_Setup], given_command: str):
        s = await setup
        # GIVEN a Telegram user whose conversation started
        await _initialize(s)
        _started(s)

        # WHEN the user sends /help, or a command the bot does not know
        actual_messages = await s.service.handle_sent_message(_message("100200300", command=given_command))

        # THEN the user gets the help text
        s.conversation_service.send.assert_not_awaited()
        assert [m.text for m in actual_messages] == [_text("help")]


@pytest.mark.asyncio
class TestBwsTasks:
    async def _given_an_open_bws_task(self, s: _Setup):
        await _initialize(s)
        _started(s)
        s.conversation_service.send.return_value = _response(_bws_message())
        actual_messages = await s.service.handle_sent_message(_message("100200300", text="Ready"))
        s.conversation_service.send.reset_mock()
        s.conversation_service.send.return_value = _response(_compass_message("Next question"))
        return actual_messages

    async def test_a_bws_task_is_answered_with_two_letters(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN Compass asks a BWS task
        # THEN the bot gets the task with the "most" prompt and the letters as choices
        actual_task_messages = await self._given_an_open_bws_task(s)
        assert len(actual_task_messages) == 1
        assert actual_task_messages[0].text.endswith(_text("bwsMostPrompt"))
        assert actual_task_messages[0].choices == ["A", "B", "C"]

        # WHEN the user picks B as the most liked
        actual_most_messages = await s.service.handle_sent_message(_message("100200300", text="b"))

        # THEN nothing is sent to the conversation yet
        s.conversation_service.send.assert_not_awaited()
        # AND the user is asked for the least liked, among the other letters
        assert [(m.text, m.choices) for m in actual_most_messages] == [(_text("bwsLeastPrompt"), ["A", "C"])]

        # WHEN the user picks C as the least liked
        actual_least_messages = await s.service.handle_sent_message(_message("100200300", text="C"))

        # THEN the answer is sent to the conversation in the JSON format of the backend
        actual_input = s.conversation_service.send.await_args.args[2]
        assert json.loads(actual_input) == {"type": "bws_response", "task_id": "0", "best": "wa.b", "worst": "wa.c"}
        # AND the bot gets the next reply of Compass
        assert [m.text for m in actual_least_messages] == ["Next question"]

        # WHEN the user then sends a letter, without an open BWS task
        s.conversation_service.send.reset_mock()
        await s.service.handle_sent_message(_message("100200300", text="A"))

        # THEN it is sent as text
        assert s.conversation_service.send.await_args.args[2] == "A"

    @pytest.mark.parametrize("given_answers, expected_prompt_key, expected_choices", [
        (["F"], "bwsMostPrompt", ["A", "B", "C"]),
        (["B", "F"], "bwsLeastPrompt", ["A", "C"]),
        (["B", "B"], "bwsLeastPrompt", ["A", "C"]),
    ], ids=["not an option as most", "not an option as least", "the same option as least"])
    async def test_an_invalid_letter_is_asked_again(self, setup: Awaitable[_Setup], given_answers: list[str],
                                                    expected_prompt_key: str, expected_choices: list[str]):
        s = await setup
        # GIVEN Compass asks a BWS task
        await self._given_an_open_bws_task(s)

        # WHEN the user answers with a letter that is not a valid option
        actual_messages = []
        for given_answer in given_answers:
            actual_messages = await s.service.handle_sent_message(_message("100200300", text=given_answer))

        # THEN nothing is sent to the conversation
        s.conversation_service.send.assert_not_awaited()
        # AND the user is asked again
        assert [(m.text, m.choices) for m in actual_messages] == [(_text(expected_prompt_key), expected_choices)]

    async def test_an_answer_in_words_is_sent_as_text(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN Compass asks a BWS task
        await self._given_an_open_bws_task(s)

        # WHEN the user answers in their own words
        await s.service.handle_sent_message(_message("100200300", text="Most B, least C"))

        # THEN the text is sent to the conversation as it is, Compass understands it
        assert s.conversation_service.send.await_args.args[2] == "Most B, least C"


@pytest.mark.asyncio
class TestTurnErrors:
    async def test_a_concluded_conversation_is_a_friendly_reply(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation is concluded
        await _initialize(s)
        _started(s)
        s.conversation_service.send.side_effect = ConversationAlreadyConcludedError(1)

        # WHEN the user sends a text
        actual_messages = await s.service.handle_sent_message(_message("100200300", text="Hi"))

        # THEN the user is told the conversation ended, and what to do
        assert [m.text for m in actual_messages] == [_text("conversationConcluded")]

    async def test_an_unexpected_error_is_a_friendly_reply(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a Telegram user whose conversation started
        await _initialize(s)
        _started(s)
        # AND the conversation turn fails
        s.conversation_service.send.side_effect = Exception("boom")

        # WHEN the user sends a text
        actual_messages = await s.service.handle_sent_message(_message("100200300", text="Hi"))

        # THEN the user is told something went wrong
        assert [m.text for m in actual_messages] == [_text("unexpectedError")]

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
