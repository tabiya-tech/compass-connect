"""
Unit tests for _ConversationLLM — ending the exploration too early.

Regression coverage for CORE-903: when the user already described their tasks while the
experiences were being collected, the LLM ended the exploration right after a brief answer
to the first question (the typical day).
"""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.agent_types import AgentInput
from app.agent.experience.work_type import WorkType
from app.agent.persona_detector import PersonaType
from app.agent.skill_explorer_agent._conversation_llm import _ConversationLLM, _FINAL_MESSAGE_KEY
from app.app_config import ApplicationConfig, set_application_config, \
    DEFAULT_SKILL_EXPLORER_MIN_QUESTIONS_BEFORE_FINISHING
from app.context_vars import user_language_ctx_var
from app.conversation_memory.conversation_memory_types import ConversationContext
from app.countries import Country
from app.i18n.translation_service import t
from app.i18n.types import Locale
from common_libs.llm.models_utils import LLMResponse

_END_OF_CONVERSATION = "<END_OF_CONVERSATION>"
_TOO_EARLY_REMINDER = "Do NOT say <END_OF_CONVERSATION>"


@pytest.fixture(autouse=True)
def _set_locale():
    token = user_language_ctx_var.set(Locale.EN_US)
    yield
    user_language_ctx_var.reset(token)


@pytest.fixture(autouse=True)
def _application_config(setup_application_config: ApplicationConfig):
    # The minimum number of questions before finishing is read from the application config
    yield setup_application_config


def _set_min_questions_before_finishing(config: ApplicationConfig, min_questions: int):
    set_application_config(config.model_copy(update={"skill_explorer_min_questions_before_finishing": min_questions}))


def _llm_response(text: str) -> LLMResponse:
    return LLMResponse(text=text, prompt_token_count=100, response_token_count=10)


async def _execute(question_asked_until_now: list[str], user_answer: str):
    return await _ConversationLLM.execute(
        experiences_explored=[],
        first_time_for_experience=False,
        question_asked_until_now=question_asked_until_now,
        user_input=AgentInput(message=user_answer),
        country_of_user=Country.ZAMBIA,
        persona_type=PersonaType.INFORMAL,
        context=ConversationContext(),
        experience_index=0,
        rich_response=False,
        experience_title="Chopping Vegetables and Washing Pots",
        work_type=WorkType.UNSEEN_UNPAID,
        logger=logging.getLogger())


@pytest.mark.asyncio
@patch("app.agent.skill_explorer_agent._conversation_llm.get_llm")
async def test_ending_too_early_retries_with_reminder(mock_get_llm):
    # GIVEN fewer questions asked than the default minimum required to end the exploration
    given_questions = ["Can you describe a typical day?"]
    assert len(given_questions) < DEFAULT_SKILL_EXPLORER_MIN_QUESTIONS_BEFORE_FINISHING
    # AND a brief answer from the user
    given_answer = "Sometimes I served the soup to people in the line."
    # AND an LLM that ends the conversation on the first attempt and asks a question on the second
    given_follow_up_question = "What was a challenge you faced while helping out in the kitchen?"
    mock_generate_content = AsyncMock(side_effect=[_llm_response(_END_OF_CONVERSATION),
                                                   _llm_response(given_follow_up_question)])
    mock_get_llm.return_value.generate_content = mock_generate_content

    # WHEN the conversation LLM is executed
    actual_output = await _execute(given_questions, given_answer)

    # THEN the conversation is not finished
    assert actual_output.finished is False
    # AND the user gets the question from the second attempt
    assert actual_output.message_for_user == given_follow_up_question
    # AND the LLM was called twice
    assert mock_generate_content.await_count == 2
    # AND the first attempt ends with the user's answer, without the reminder
    first_llm_input = mock_generate_content.await_args_list[0].kwargs["llm_input"]
    assert first_llm_input.turns[-1].content == given_answer
    # AND the second attempt reminds the LLM after the user's answer that it is too early to end
    # (the formatter merges the reminder into the user's turn)
    second_llm_input = mock_generate_content.await_args_list[1].kwargs["llm_input"]
    assert second_llm_input.turns[-1].content.startswith(given_answer)
    assert _TOO_EARLY_REMINDER in second_llm_input.turns[-1].content


@pytest.mark.asyncio
@patch("app.agent.skill_explorer_agent._conversation_llm.get_llm")
async def test_ending_after_enough_questions_finishes(mock_get_llm):
    # GIVEN as many questions asked as the default minimum required to end the exploration
    given_questions = ["Can you describe a typical day?", "What was a challenge you faced?"]
    assert len(given_questions) == DEFAULT_SKILL_EXPLORER_MIN_QUESTIONS_BEFORE_FINISHING
    # AND an LLM that ends the conversation
    mock_generate_content = AsyncMock(return_value=_llm_response(_END_OF_CONVERSATION))
    mock_get_llm.return_value.generate_content = mock_generate_content

    # WHEN the conversation LLM is executed
    actual_output = await _execute(given_questions, "It was hard to stand all day.")

    # THEN the conversation is finished with the final message
    assert actual_output.finished is True
    assert actual_output.message_for_user == t("messages", _FINAL_MESSAGE_KEY)
    # AND the LLM was called only once
    assert mock_generate_content.await_count == 1


@pytest.mark.asyncio
@patch("app.agent.skill_explorer_agent._conversation_llm.get_llm")
async def test_ending_too_early_uses_the_configured_minimum(mock_get_llm, _application_config: ApplicationConfig):
    # GIVEN a configured minimum of questions higher than the default
    given_min_questions = DEFAULT_SKILL_EXPLORER_MIN_QUESTIONS_BEFORE_FINISHING + 1
    _set_min_questions_before_finishing(_application_config, given_min_questions)
    # AND as many questions asked as the default minimum, but fewer than the configured one
    given_questions = ["Can you describe a typical day?", "What was a challenge you faced?"]
    assert len(given_questions) == DEFAULT_SKILL_EXPLORER_MIN_QUESTIONS_BEFORE_FINISHING
    # AND an LLM that ends the conversation on the first attempt and asks a question on the second
    given_follow_up_question = "What tasks were not part of your role?"
    mock_generate_content = AsyncMock(side_effect=[_llm_response(_END_OF_CONVERSATION),
                                                   _llm_response(given_follow_up_question)])
    mock_get_llm.return_value.generate_content = mock_generate_content

    # WHEN the conversation LLM is executed
    actual_output = await _execute(given_questions, "It was hard to stand all day.")

    # THEN the conversation is not finished
    assert actual_output.finished is False
    # AND the user gets the question from the second attempt
    assert actual_output.message_for_user == given_follow_up_question


@pytest.mark.asyncio
@patch("app.agent.skill_explorer_agent._conversation_llm.get_llm")
async def test_ending_after_the_first_question_finishes_when_the_minimum_is_one(mock_get_llm,
                                                                                _application_config: ApplicationConfig):
    # GIVEN a configured minimum of one question, which turns off the check
    _set_min_questions_before_finishing(_application_config, 1)
    # AND only the first question asked
    given_questions = ["Can you describe a typical day?"]
    # AND an LLM that ends the conversation
    mock_generate_content = AsyncMock(return_value=_llm_response(_END_OF_CONVERSATION))
    mock_get_llm.return_value.generate_content = mock_generate_content

    # WHEN the conversation LLM is executed
    actual_output = await _execute(given_questions, "Sometimes I served the soup to people in the line.")

    # THEN the conversation is finished with the final message
    assert actual_output.finished is True
    assert actual_output.message_for_user == t("messages", _FINAL_MESSAGE_KEY)
    # AND the LLM was called only once
    assert mock_generate_content.await_count == 1


@pytest.mark.asyncio
@patch("app.agent.skill_explorer_agent._conversation_llm.get_llm")
async def test_ending_too_early_on_every_attempt_falls_back_to_finishing(mock_get_llm):
    # GIVEN fewer questions asked than required to end the exploration
    given_questions = ["Can you describe a typical day?"]
    # AND an LLM that ends the conversation on every attempt
    # (a new response per attempt, as the response text is replaced with the final message)
    mock_generate_content = AsyncMock(side_effect=lambda **_: _llm_response(_END_OF_CONVERSATION))
    mock_get_llm.return_value.generate_content = mock_generate_content

    # WHEN the conversation LLM is executed
    actual_output = await _execute(given_questions, "Sometimes I served the soup to people in the line.")

    # THEN after all the retries the conversation is finished with the final message
    assert actual_output.finished is True
    assert actual_output.message_for_user == t("messages", _FINAL_MESSAGE_KEY)
    # AND the LLM was called once per retry
    assert mock_generate_content.await_count == 3
