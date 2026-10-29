from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_mock

from app.agent.agent_director.abstract_agent_director import ConversationPhase
from app.application_state import ApplicationState
from app.conversation_memory.conversation_memory_types import ConversationContext, ConversationHistory
from app.conversations.service import ConversationService, ConversationAlreadyConcludedError
from app.integration.webhooks.notifier import WebhookNotifier
from app.integration.webhooks.types import WebhookEvent

_USER_ID = "uid-1"
_SESSION_ID = 123


def _service(state: ApplicationState, phase_after_the_turn: ConversationPhase,
             webhook_notifier: AsyncMock) -> ConversationService:
    """
    A conversation service whose agents move the conversation to `phase_after_the_turn` when they handle the turn.
    """
    recorder = AsyncMock()
    recorder.get_state.return_value = state

    agent_director = MagicMock()

    async def _handle_the_turn(user_input):
        state.agent_director_state.current_phase = phase_after_the_turn

    agent_director.execute = AsyncMock(side_effect=_handle_the_turn)

    memory_manager = MagicMock()
    memory_manager.get_conversation_context = AsyncMock(
        return_value=ConversationContext(all_history=ConversationHistory(), history=ConversationHistory()))

    return ConversationService(application_state_metrics_recorder=recorder, agent_director=agent_director,
                               conversation_memory_manager=memory_manager, reaction_repository=AsyncMock(),
                               job_preferences_service=AsyncMock(), user_recommendations_service=AsyncMock(),
                               webhook_notifier=webhook_notifier)


def _state_in(phase: ConversationPhase) -> ApplicationState:
    state = ApplicationState.new_state(_SESSION_ID)
    state.agent_director_state.current_phase = phase
    return state


async def _send_a_turn(service: ConversationService):
    return await service.send(_USER_ID, _SESSION_ID, "hola", clear_memory=False, filter_pii=False)


@pytest.fixture(autouse=True)
def _no_messages_to_build(mocker: pytest_mock.MockerFixture):
    # the messages of the turn are not what these tests are about: the agents here add none
    mocker.patch("app.conversations.service.get_messages_from_conversation_manager", AsyncMock(return_value=[]))


@pytest.mark.usefixtures("setup_application_config")  # the turn reads the language from the config
class TestWebhookOnConversationEnd:
    @pytest.mark.asyncio
    async def test_the_turn_that_ends_the_conversation_notifies(self):
        # GIVEN a conversation in its last phase
        given_notifier = AsyncMock(spec=WebhookNotifier)
        service = _service(_state_in(ConversationPhase.CHECKOUT), ConversationPhase.ENDED, given_notifier)

        # WHEN the user sends the turn that ends it
        actual = await _send_a_turn(service)

        # THEN the user is told it is completed, and conversation.completed is emitted for this user and session
        assert actual.conversation_completed is True
        given_notifier.emit.assert_awaited_once_with(WebhookEvent.CONVERSATION_COMPLETED, _USER_ID,
                                                     {"session_id": _SESSION_ID})

    @pytest.mark.asyncio
    async def test_a_turn_that_does_not_end_it_does_not_notify(self):
        given_notifier = AsyncMock(spec=WebhookNotifier)
        service = _service(_state_in(ConversationPhase.COUNSELING), ConversationPhase.COUNSELING, given_notifier)

        actual = await _send_a_turn(service)

        assert actual.conversation_completed is False
        given_notifier.emit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_turn_on_an_ended_conversation_does_not_notify_again(self):
        given_notifier = AsyncMock(spec=WebhookNotifier)
        service = _service(_state_in(ConversationPhase.ENDED), ConversationPhase.ENDED, given_notifier)

        with pytest.raises(ConversationAlreadyConcludedError):
            await _send_a_turn(service)

        given_notifier.emit.assert_not_awaited()
