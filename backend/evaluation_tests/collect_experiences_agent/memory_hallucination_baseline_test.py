"""
Baseline evaluation test for memory recall accuracy after conversation summarization.

PURPOSE:
    Verify (and measure) whether the chatbot hallucinates or blends experience details
    when recalling a specific past experience after the conversation history has been
    compressed by the summarizer.

BACKGROUND:
    The ConversationMemoryManager uses a sliding window:
      - UNSUMMARIZED_WINDOW_SIZE = 10 (turns kept verbatim)
      - TO_BE_SUMMARIZED_WINDOW_SIZE = 3 (turns staged before compression)
    Summarization first fires at turn 13, then every 3 turns after that.

    The summarizer uses gemini-2.5-flash-lite with HIGH_TEMPERATURE and a 100-word cap,
    instructed to "capture essence not details" — meaning specific experience details
    are at high risk of being dropped or blended after compression.

WHAT THIS TEST MEASURES:
    Two experiences are collected in the first 12 turns:
      1. PAID: Data Entry Clerk at a telecom company (entering data, filing forms)
      2. VOLUNTEERING: Survey Enumerator at an NGO (asking questions, recording answers,
         convincing hesitant respondents)

    After summarization fires, filler turns push early experience details out of the
    verbatim window. Then the user asks a direct recall question:
        "Can you remind me what I said I volunteered for?"

    The test scores whether the agent recalls the correct (volunteering) details
    without hallucinating or blending in the paid (data entry/telecom) details.

PASS CRITERIA:
    Score >= 60/100 across 5 repeated runs signals acceptable recall.
    Score < 60 on 3+ of 5 runs confirms the hallucination bug at 60-80% frequency.
"""

import logging
import os
from typing import Coroutine, Callable, Awaitable

import pytest
from _pytest.logging import LogCaptureFixture

from app.conversation_memory.conversation_memory_manager import ConversationMemoryManager, \
    ConversationMemoryManagerState
from app.countries import Country
from app.i18n.translation_service import get_i18n_manager
from app.server_config import UNSUMMARIZED_WINDOW_SIZE, TO_BE_SUMMARIZED_WINDOW_SIZE
from common_libs.test_utilities import get_random_session_id
from common_libs.test_utilities.guard_caplog import guard_caplog, assert_log_error_warnings
from evaluation_tests.collect_experiences_agent.collect_experiences_executor import CollectExperiencesAgentExecutor, \
    CollectExperienceAgentGetConversationContextExecutor, CollectExperienceAgentIsFinished
from evaluation_tests.conversation_libs.conversation_test_function import conversation_test_function, \
    ConversationTestConfig, ScriptedUserEvaluationTestCase, ScriptedSimulatedUser, Evaluation
from evaluation_tests.conversation_libs.evaluators.evaluation_result import EvaluationType


@pytest.fixture(scope="function")
async def setup_collect_experiences_agent() -> tuple[
    ConversationMemoryManager,
    Callable[
        [LogCaptureFixture, ScriptedUserEvaluationTestCase, Country],
        Coroutine[None, None, None]
    ]
]:
    session_id = get_random_session_id()
    # Use a smaller window to force summarization to fire during the conversation
    # (at turn 5 rather than turn 13) so that early experience details get
    # compressed before the recall probe is reached.
    conversation_manager = ConversationMemoryManager(
        unsummarized_window_size=2,
        to_be_summarized_window_size=3
    )
    conversation_manager.set_state(state=ConversationMemoryManagerState(session_id=session_id))

    async def collect_experiences_exec(caplog: LogCaptureFixture, test_case: ScriptedUserEvaluationTestCase,
                                       country: Country):
        get_i18n_manager().set_locale(test_case.locale)
        output_folder = os.path.join(os.getcwd(),
                                     'test_output/collect_experiences_agent/memory_hallucination', test_case.name)
        execute_evaluated_agent = CollectExperiencesAgentExecutor(
            conversation_manager=conversation_manager,
            session_id=session_id,
            country_of_user=country
        )

        config = ConversationTestConfig(
            max_iterations=len(test_case.scripted_user),
            test_case=test_case,
            output_folder=output_folder,
            execute_evaluated_agent=execute_evaluated_agent,
            execute_simulated_user=ScriptedSimulatedUser(script=test_case.scripted_user),
            # Do NOT stop early on work-type completion — the recall probe must be reached.
            # Only stop when the script runs out of turns.
            is_finished=CollectExperienceAgentIsFinished(executor=None),
            get_conversation_context=CollectExperienceAgentGetConversationContextExecutor(
                conversation_manager=conversation_manager)
        )

        with caplog.at_level(logging.DEBUG):
            guard_caplog(logger=execute_evaluated_agent._agent._logger, caplog=caplog)
            await conversation_test_function(config=config)
            assert_log_error_warnings(caplog=caplog,
                                      expect_errors_in_logs=False,
                                      expect_warnings_in_logs=True)

    return conversation_manager, collect_experiences_exec


@pytest.mark.asyncio
@pytest.mark.evaluation_test("gemini-3.5-flash-lite/")
@pytest.mark.repeat(5)
async def test_memory_recall_accuracy_after_summarization(
        caplog: LogCaptureFixture,
        setup_collect_experiences_agent: Awaitable[tuple[
            ConversationMemoryManager,
            Callable[[LogCaptureFixture, ScriptedUserEvaluationTestCase, Country], Coroutine[None, None, None]]
        ]],
        setup_multi_locale_app_config):
    """
    Measures hallucination rate when recalling a specific past experience after
    conversation summarization has fired.

    This test uses a reduced window size (unsummarized=2, to_be_summarized=3) so that
    summarization fires at turn 5 and again at turn 8, compressing the paid experience
    details well before the recall probe at turn 12.

    Conversation is designed to:
      - Collect a PAID experience (Data Entry Clerk, telecom, entering data/filing) in turns 1-6
        → summarization fires at turns 5 and 8, compressing these details into <=100 words
      - Collect a VOLUNTEERING experience (Survey Enumerator, NGO, asking questions/recording
        answers/convincing respondents) in turns 7-11
      - Ask the recall probe at turn 12 (mid-conversation, before agent finishes):
          "wait, before we continue — can you remind me what I said I volunteered for"

    The MEMORY_RECALL_ACCURACY evaluator scores whether the agent's recall response:
      - Correctly describes the Survey Enumerator / NGO role (score 86-100)
      - Partially blends in paid experience details (score 31-60)
      - Fully hallucinates or describes the wrong experience (score 0-30)

    A pass threshold of 60 is set. If the test fails on 3+ of 5 runs, this confirms
    the hallucination bug at ~60-80% frequency and justifies the memory architecture fix.
    """

    given_test_case = ScriptedUserEvaluationTestCase(
        name='memory_recall_accuracy_after_summarization',
        simulated_user_prompt=(
            "Scripted user: Zambian user with two experiences - "
            "a paid data entry job at a telecom and an unpaid volunteering role as a survey enumerator at an NGO."
        ),
        scripted_user=[
            # --- Turns 1-6: Collect PAID experience (Data Entry Clerk, telecom) ---
            # With unsummarized_window=2 and to_be_summarized_window=3,
            # summarization first fires at turn 5 (2+3), compressing turns 1-3.
            # By turn 8 the paid experience details are fully summarized away.
            #
            # Turn 1: agent asks if user has worked
            "yes",
            # Turn 2: agent asks about paid work
            "I worked as a Data Entry Clerk at Zamtel, a telecom company here in Lusaka",
            # Turn 3: agent asks about dates
            "I was there from January 2021 to December 2022",
            # Turn 4: agent asks about location
            "Lusaka, Cairo Road branch",
            # Turn 5: agent asks about duties or follows up — summarization fires here
            "My main work was entering customer data into their billing system and filing forms and organising paper records",
            # Turn 6: agent asks if there are more paid experiences
            "no, that was my only paid job",

            # --- Turns 7-11: Collect VOLUNTEERING experience (Survey Enumerator, NGO) ---
            # By now the paid experience is in the summary (compressed).
            # Turn 7: agent transitions to unpaid/volunteering
            "yes I have done some volunteering",
            # Turn 8: agent asks about the volunteering role — summarization fires again (turns 4-6 compressed)
            "I volunteered as a Survey Enumerator for a local NGO called Community Voice Zambia",
            # Turn 9: agent asks about dates
            "it was in 2020, for about three months",
            # Turn 10: agent asks about location
            "we worked in Kabwe and surrounding townships",
            # Turn 11: agent asks about duties
            "we would go door to door asking people questions and recording their answers. sometimes you had to gently convince people who did not want to participate",

            # --- Turn 12: RECALL PROBE — asked before finishing ---
            # Paid experience details have now been through 2 summarization cycles.
            # Volunteering details are still in the unsummarized window.
            # This is the critical turn being evaluated.
            "wait, before we continue — can you remind me what I said I volunteered for",

            # --- Turn 13: finish the collection ---
            "no that is the only volunteering I did",
        ],
        evaluations=[
            Evaluation(
                type=EvaluationType.MEMORY_RECALL_ACCURACY,
                # Minimum acceptable score: agent must get the volunteering details
                # mostly right without blending the paid experience in.
                # A score below 60 = partial-to-full hallucination = bug confirmed.
                expected=60
            )
        ]
    )

    conversation_manager, collect_experiences_exec = await setup_collect_experiences_agent
    await collect_experiences_exec(caplog, given_test_case, Country.ZAMBIA)
