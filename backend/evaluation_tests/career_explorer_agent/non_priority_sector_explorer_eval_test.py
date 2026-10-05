"""
Evaluation tests for NonPrioritySectorExplorer.
Uses CriteriaEvaluator (LLM) to assess that web search responses for non-priority sectors
are substantive, informative, and stay on career-related topics.
"""

import logging
from dataclasses import dataclass

import pytest

from app.app_config import get_application_config, set_application_config
from app.career_explorer.config import CareerExplorerConfig
from app.i18n.translation_service import get_i18n_manager
from app.i18n.types import Locale
from evaluation_tests.conversation_libs.evaluators.criteria_evaluator import CriteriaEvaluator
from evaluation_tests.conversation_libs.evaluators.evaluation_result import (
    Actor,
    ConversationEvaluationRecord,
    ConversationRecord,
    EvaluationType,
)
from evaluation_tests.conversation_libs.fake_conversation_context import FakeConversationContext
from app.agent.career_explorer_agent.non_priority_sector_explorer import NonPrioritySectorExplorer

DEFAULT_SECTORS = [
    {"name": "Agriculture", "description": "Commercial farming", "file": "agriculture.md"},
    {"name": "Mining", "description": "Copper, gold", "file": "mining.md"},
]

MIN_LLM_SCORE = 60


@dataclass
class NonPriorityExplorerTestCase:
    name: str
    user_input: str


NON_PRIORITY_EXPLORER_TEST_CASES = [
    NonPriorityExplorerTestCase("aeronautical_engineering", "I want to talk about aeronautical engineering"),
    NonPriorityExplorerTestCase("software_development", "What about careers in software development?"),
]


@pytest.fixture
def career_explorer_config_with_sectors(setup_multi_locale_app_config):
    config = get_application_config()
    updated = config.model_copy(
        update={"career_explorer_config": CareerExplorerConfig(sectors=DEFAULT_SECTORS, country="Zambia")}
    )
    set_application_config(updated)
    yield updated


@pytest.mark.asyncio
@pytest.mark.evaluation_test("gemini-3.5-flash-lite/")
@pytest.mark.parametrize("test_case", NON_PRIORITY_EXPLORER_TEST_CASES, ids=[tc.name for tc in NON_PRIORITY_EXPLORER_TEST_CASES])
async def test_non_priority_sector_explorer_web_search(
    evals_setup,
    career_explorer_config_with_sectors,
    test_case: NonPriorityExplorerTestCase,
):
    """
    Non-priority explorer uses Google Search. Uses CriteriaEvaluator (LLM) to assess response quality:
    substantive career information, no deflection to priority sectors.
    """
    get_i18n_manager().set_locale(Locale.EN_US)

    context = FakeConversationContext()
    context.add_turn("", "Welcome! Which sector interests you?")
    context.add_turn(test_case.user_input, "")

    explorer = NonPrioritySectorExplorer()
    message, finished, _, _, grounding_metadata = await explorer.explore(
        user_input=test_case.user_input,
        context=context,
    )

    evaluation_record = ConversationEvaluationRecord(
        test_case=test_case.name,
        simulated_user_prompt=test_case.user_input,
        conversation=[
            ConversationRecord(message="Welcome! Which sector interests you?", actor=Actor.SIMULATED_USER),
            ConversationRecord(message=test_case.user_input, actor=Actor.SIMULATED_USER),
            ConversationRecord(message=message, actor=Actor.EVALUATED_AGENT),
        ],
    )

    evaluator = CriteriaEvaluator(criteria=EvaluationType.NON_PRIORITY_SECTOR_RESPONSE_QUALITY)
    eval_result = await evaluator.evaluate(evaluation_record)

    logging.info(
        "Non-priority explorer test %s: response message (first 500 chars): %s",
        test_case.name,
        message[:500] if message else "(empty)",
    )
    if grounding_metadata:
        logging.info(
            "Non-priority explorer test %s: got %d sources from web search, LLM score=%d (%s)",
            test_case.name,
            len(grounding_metadata.grounding_chunks),
            eval_result.score,
            eval_result.reasoning[:100],
        )
    else:
        logging.info(
            "Non-priority explorer test %s: LLM score=%d (%s)",
            test_case.name,
            eval_result.score,
            eval_result.reasoning[:100],
        )

    assert eval_result.score >= MIN_LLM_SCORE, (
        f"Expected LLM evaluation score >= {MIN_LLM_SCORE} for substantive career response, "
        f"got {eval_result.score}. Reasoning: {eval_result.reasoning}"
    )
