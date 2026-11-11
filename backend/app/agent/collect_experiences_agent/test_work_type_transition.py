"""
Tests for the message the user sees when the CollectExperiencesAgent moves from one work type to the next
(e.g. the user answers "no" to paid work and the agent moves on to unpaid work).
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.collect_experiences_agent._transition_decision_tool import TransitionDecision
from app.agent.collect_experiences_agent.collect_experiences_agent import (
    CollectExperiencesAgent,
    CollectExperiencesAgentState,
)
from app.agent.collect_experiences_agent.test_quick_reply_options import (  # pylint: disable=unused-import
    _make_context,
    _make_conversation_llm_output,
    _make_transition_result,
    _make_user_input,
    setup_application_config,
)
from app.agent.experience.work_type import WorkType
from common_libs.test_utilities import get_random_session_id

_CONVERSATION_LLM_EXECUTE = "app.agent.collect_experiences_agent.collect_experiences_agent._ConversationLLM.execute"
_TRANSITION_TOOL_EXECUTE = "app.agent.collect_experiences_agent.collect_experiences_agent.TransitionDecisionTool.execute"


def _given_agent_exploring_paid_work() -> CollectExperiencesAgent:
    given_state = CollectExperiencesAgentState(
        session_id=get_random_session_id(),
        first_time_visit=False,
        unexplored_types=[WorkType.PAID_WORK, WorkType.UNPAID_WORK],
        explored_types=[],
    )
    given_agent = CollectExperiencesAgent()
    given_agent.set_state(given_state)
    return given_agent


class TestWorkTypeTransitionMessage:
    """Tests that the user is asked about the next work type in the same turn the previous one ends."""

    @pytest.mark.asyncio
    @patch(_CONVERSATION_LLM_EXECUTE, new_callable=AsyncMock)
    @patch(_TRANSITION_TOOL_EXECUTE, new_callable=AsyncMock)
    async def test_end_worktype_returns_opening_question_for_next_type(
            self, mock_transition, mock_conversation_llm, setup_application_config
    ):
        """should ask about unpaid work in the same turn the user says they have no (more) paid work"""
        # GIVEN an agent exploring paid work, with unpaid work still to explore
        given_agent = _given_agent_exploring_paid_work()
        # AND the conversation LLM first returns the generic move-on text (generated for paid work),
        # and then the opening question for unpaid work
        given_move_on_output = _make_conversation_llm_output("Let's move on to other work experiences.")
        given_opening_output = _make_conversation_llm_output("Have you done any unpaid work?",
                                                             metadata={"quick_reply_options": [{"label": "Yes"}, {"label": "No"}]})
        mock_conversation_llm.side_effect = [given_move_on_output, given_opening_output]
        # AND the transition tool decides to end the paid work type
        mock_transition.return_value = _make_transition_result(TransitionDecision.END_WORKTYPE)

        # WHEN the agent is executed
        actual_output = await given_agent.execute(_make_user_input(""), _make_context())

        # THEN the user is asked the opening question for unpaid work, with its quick replies
        assert actual_output.message_for_user == "Have you done any unpaid work?"
        assert actual_output.metadata == {"quick_reply_options": [{"label": "Yes"}, {"label": "No"}]}
        # AND the conversation is not finished
        assert actual_output.finished is False
        # AND paid work is explored and unpaid work is the current type
        assert given_agent._state.explored_types == [WorkType.PAID_WORK]
        assert given_agent._state.unexplored_types == [WorkType.UNPAID_WORK]
        # AND the opening question was generated with the first-visit prompt for unpaid work
        assert mock_conversation_llm.call_count == 2
        actual_second_call = mock_conversation_llm.call_args_list[1].kwargs
        assert actual_second_call["first_time_visit"] is True
        assert actual_second_call["exploring_type"] == WorkType.UNPAID_WORK
        # AND the LLM stats of both calls are kept (move-on call + transition tool + opening call)
        assert len(actual_output.llm_stats) == 3

    @pytest.mark.asyncio
    @patch(_CONVERSATION_LLM_EXECUTE, new_callable=AsyncMock)
    @patch(_TRANSITION_TOOL_EXECUTE, new_callable=AsyncMock)
    async def test_end_worktype_keeps_previous_message_when_opening_fails(
            self, mock_transition, mock_conversation_llm, setup_application_config
    ):
        """should keep the previous message if the opening question for the next type cannot be generated"""
        # GIVEN an agent exploring paid work, with unpaid work still to explore
        given_agent = _given_agent_exploring_paid_work()
        # AND the conversation LLM returns an unusable (empty) opening message on the second call
        given_move_on_output = _make_conversation_llm_output("Let's move on to other work experiences.")
        mock_conversation_llm.side_effect = [given_move_on_output, _make_conversation_llm_output("  ")]
        # AND the transition tool decides to end the paid work type
        mock_transition.return_value = _make_transition_result(TransitionDecision.END_WORKTYPE)

        # WHEN the agent is executed
        actual_output = await given_agent.execute(_make_user_input(""), _make_context())

        # THEN the previous message is returned
        assert actual_output.message_for_user == "Let's move on to other work experiences."
        # AND the work type still advanced
        assert given_agent._state.unexplored_types == [WorkType.UNPAID_WORK]

    @pytest.mark.asyncio
    @patch(_CONVERSATION_LLM_EXECUTE, new_callable=AsyncMock)
    @patch(_TRANSITION_TOOL_EXECUTE, new_callable=AsyncMock)
    async def test_continue_does_not_generate_an_opening_question(
            self, mock_transition, mock_conversation_llm, setup_application_config
    ):
        """should not call the conversation LLM again when staying on the same work type"""
        # GIVEN an agent exploring paid work
        given_agent = _given_agent_exploring_paid_work()
        mock_conversation_llm.return_value = _make_conversation_llm_output("Where did you work?")
        # AND the transition tool decides to continue
        mock_transition.return_value = _make_transition_result(TransitionDecision.CONTINUE)

        # WHEN the agent is executed
        actual_output = await given_agent.execute(_make_user_input(""), _make_context())

        # THEN the conversation LLM message is returned as is
        assert actual_output.message_for_user == "Where did you work?"
        # AND the conversation LLM was called only once
        assert mock_conversation_llm.call_count == 1

    @pytest.mark.asyncio
    @patch(_CONVERSATION_LLM_EXECUTE, new_callable=AsyncMock)
    @patch(_TRANSITION_TOOL_EXECUTE, new_callable=AsyncMock)
    async def test_end_worktype_of_last_type_finishes_without_opening_question(
            self, mock_transition, mock_conversation_llm, setup_application_config
    ):
        """should finish the collection without another LLM call when the last work type ends"""
        # GIVEN an agent exploring unpaid work, the last type
        given_state = CollectExperiencesAgentState(
            session_id=get_random_session_id(),
            first_time_visit=False,
            unexplored_types=[WorkType.UNPAID_WORK],
            explored_types=[WorkType.PAID_WORK],
        )
        given_agent = CollectExperiencesAgent()
        given_agent.set_state(given_state)
        mock_conversation_llm.return_value = _make_conversation_llm_output("Thanks!")
        # AND the transition tool decides to end the work type
        mock_transition.return_value = _make_transition_result(TransitionDecision.END_WORKTYPE)

        # WHEN the agent is executed
        actual_output = await given_agent.execute(_make_user_input(""), _make_context())

        # THEN the collection is finished
        assert actual_output.finished is True
        # AND the conversation LLM was called only once
        assert mock_conversation_llm.call_count == 1
