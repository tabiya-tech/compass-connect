import logging
import os
from dataclasses import dataclass, field

import pytest

from app.app_config import get_application_config, set_application_config
from app.career_explorer.config import CareerExplorerConfig
from app.i18n.translation_service import get_i18n_manager
from app.i18n.types import Locale
from evaluation_tests.conversation_libs.conversation_generator import generate
from evaluation_tests.conversation_libs.conversation_test_function import ScriptedSimulatedUser
from evaluation_tests.conversation_libs.evaluators.evaluation_result import Actor, ConversationRecord
from evaluation_tests.career_explorer_agent.career_explorer_agent_executors import (
    CareerExplorerExecutor,
    CareerExplorerGetConversationContextExecutor,
    CareerExplorerIsFinished,
)
from app.conversation_memory.save_conversation_context import (
    save_conversation_context_to_json,
    save_conversation_context_to_markdown,
)

DEFAULT_SECTORS = [
    {"name": "Agriculture", "description": "Commercial farming", "file": "agriculture.md"},
    {"name": "Mining", "description": "Copper, gold", "file": "mining.md"},
]


@dataclass
class SectorContentTestCase:
    """Test case with scripted questions and expected phrases from RAG content."""
    name: str
    scripted_user: list[str]
    description: str
    expected_phrases_by_turn: list[list[str]] = field(default_factory=list)
    """
    For each agent response, at least one phrase in the list must appear.
    Turn 0 = welcome message. Turn 1 = response to scripted_user[0], etc.
    """


TEST_CASES_GENERAL_KNOWLEDGE = [
    SectorContentTestCase(
        name="general_knowledge_no_rag_data",
        description="User asks a question unlikely to be in local embeddings — agent should use general knowledge with hedging",
        scripted_user=[
            "What soft skills do I need to advance my career in mining?",
        ],
        expected_phrases_by_turn=[
            ["Welcome", "priority sectors", "sectors", "careers", "explore"],
            # Should answer substantively from general knowledge, not refuse
            ["communication", "teamwork", "leadership", "problem", "skills", "generally", "typically", "industry"],
        ],
    ),
    SectorContentTestCase(
        name="general_knowledge_career_progression",
        description="User asks about career progression path — general concept unlikely to be fully covered in local data",
        scripted_user=[
            "How do I grow from an entry-level role to a senior position in agriculture?",
        ],
        expected_phrases_by_turn=[
            ["Welcome", "priority sectors", "sectors", "careers", "explore"],
            # Should give a substantive progression answer, not "I don't know"
            ["experience", "senior", "progression", "grow", "skills", "generally", "typically", "career", "years"],
        ],
    ),
]

TEST_CASES = [
    SectorContentTestCase(
        name="ask_agriculture",
        description="User asks about Agriculture sector",
        scripted_user=[
            "Tell me about Agriculture",
        ],
        expected_phrases_by_turn=[
            ["Welcome", "priority sectors", "sectors", "careers", "explore"],
            ["Agriculture", "irrigation", "Zambeef", "TEVET", "commercial", "aquaculture", "crop"],
        ],
    ),
    SectorContentTestCase(
        name="ask_mining",
        description="User asks about Mining sector",
        scripted_user=[
            "What roles are there in mining?",
        ],
        expected_phrases_by_turn=[
            ["Welcome", "priority sectors", "sectors", "careers", "explore"],
            ["Mining", "Copperbelt", "Barrick", "Heavy Equipment", "gemstone", "K7,500", "Driller"],
        ],
    ),
    SectorContentTestCase(
        name="ask_agriculture_then_mining",
        description="User asks about Agriculture then Mining",
        scripted_user=[
            "I'm interested in Agriculture",
            "What about mining?",
        ],
        expected_phrases_by_turn=[
            ["Welcome", "priority sectors", "sectors", "careers", "explore"],
            ["Agriculture", "irrigation", "Zambeef", "TEVET", "commercial", "aquaculture"],
            ["Mining", "Copperbelt", "Barrick", "Heavy Equipment", "gemstone", "K7,500"],
        ],
    ),
    SectorContentTestCase(
        name="ask_mining_then_reference_previous",
        description="User asks about mining, then references previous conversation",
        scripted_user=[
            "What roles are there in mining?",
            "Tell me more about the roles you mentioned",
        ],
        expected_phrases_by_turn=[
            ["Welcome", "priority sectors", "sectors", "careers", "explore"],
            ["Mining", "roles", "Heavy Equipment", "Driller", "Copperbelt"],
            ["roles", "mining", "Heavy Equipment", "Driller", "mentioned"],
        ],
    ),
    SectorContentTestCase(
        name="ask_agriculture_then_ask_specific_followup",
        description="User asks about agriculture, then asks a specific follow-up question",
        scripted_user=[
            "I'm interested in Agriculture",
            "What skills do I need for the roles you mentioned?",
        ],
        expected_phrases_by_turn=[
            ["Welcome", "priority sectors", "sectors", "careers", "explore"],
            ["Agriculture", "irrigation", "Zambeef", "TEVET", "commercial", "aquaculture"],
            ["skills", "roles", "Agriculture", "irrigation", "TEVET"],
        ],
    ),
    SectorContentTestCase(
        name="multi_turn_context_preservation",
        description="Multi-turn conversation testing context preservation",
        scripted_user=[
            "Tell me about mining",
            "What about the salary you mentioned?",
            "And what about agriculture?",
        ],
        expected_phrases_by_turn=[
            ["Welcome", "priority sectors", "sectors", "careers", "explore"],
            ["Mining", "Copperbelt", "Barrick", "Heavy Equipment", "gemstone", "K7,500"],
            ["salary", "K7,500", "earn", "mining"],
            ["Agriculture", "irrigation", "Zambeef", "TEVET", "commercial"],
        ],
    ),
]


def _agent_responses(conversation: list[ConversationRecord]) -> list[str]:
    return [r.message for r in conversation if r.actor == Actor.EVALUATED_AGENT]


def _assert_rag_content(conversation: list[ConversationRecord], test_case: SectorContentTestCase) -> None:
    agent_responses = _agent_responses(conversation)
    assert len(agent_responses) >= len(test_case.expected_phrases_by_turn), (
        f"Expected at least {len(test_case.expected_phrases_by_turn)} agent responses, "
        f"got {len(agent_responses)}"
    )
    for i, expected_phrases in enumerate(test_case.expected_phrases_by_turn):
        if i >= len(agent_responses):
            break
        response_text = agent_responses[i].lower()
        found = any(phrase.lower() in response_text for phrase in expected_phrases)
        excerpt = agent_responses[i][:400] + "..." if len(agent_responses[i]) > 400 else agent_responses[i]
        user_message = ""
        if i > 0 and i - 1 < len(test_case.scripted_user):
            user_message = f" (in response to '{test_case.scripted_user[i - 1]}')"
        assert found, (
            f"Agent response {i}{user_message} should contain "
            f"at least one of {expected_phrases} but got: {excerpt}"
        )


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
@pytest.mark.parametrize("test_case", TEST_CASES, ids=[tc.name for tc in TEST_CASES])
async def test_career_explorer_sector_content(
    evals_setup, setup_multi_locale_app_config, career_explorer_config_with_sectors, test_case: SectorContentTestCase
):
    """
    Scripted conversation test. Asserts agent responses include content from the
    embedded sector markdown files (simulated via mock RAG).
    """
    logging.info("Running Career Explorer test case: %s", test_case.name)
    get_i18n_manager().set_locale(Locale.EN_US)

    executor = CareerExplorerExecutor()
    max_iterations = len(test_case.scripted_user) + 1

    conversation = await generate(
        max_iterations=max_iterations,
        execute_evaluated_agent=executor,
        execute_simulated_user=ScriptedSimulatedUser(script=test_case.scripted_user),
        is_finished=CareerExplorerIsFinished(),
    )

    _assert_rag_content(conversation, test_case)

    output_folder = os.path.join(
        os.getcwd(),
        "test_output",
        "career_explorer_agent",
        "scripted",
        test_case.name,
    )
    os.makedirs(output_folder, exist_ok=True)

    from datetime import datetime, timezone
    time_now = datetime.now(timezone.utc).isoformat()
    base_name = f"{test_case.name}_{time_now}"

    from evaluation_tests.conversation_libs.evaluators.evaluation_result import ConversationEvaluationRecord
    record = ConversationEvaluationRecord(
        simulated_user_prompt=test_case.description,
        test_case=test_case.name,
    )
    record.add_conversation_records(conversation)
    record.save_data(folder=output_folder, base_file_name=base_name)

    context = await CareerExplorerGetConversationContextExecutor(executor)()
    ctx_path = os.path.join(output_folder, f"{base_name}_context")
    save_conversation_context_to_json(context=context, file_path=ctx_path + ".json")
    save_conversation_context_to_markdown(
        title=f"Career Explorer: {test_case.name}",
        context=context,
        file_path=ctx_path + ".md",
    )


@pytest.mark.asyncio
@pytest.mark.evaluation_test("gemini-3.5-flash-lite/")
@pytest.mark.parametrize(
    "test_case", TEST_CASES_GENERAL_KNOWLEDGE, ids=[tc.name for tc in TEST_CASES_GENERAL_KNOWLEDGE]
)
async def test_career_explorer_general_knowledge_fallback(
    evals_setup, setup_multi_locale_app_config, career_explorer_config_with_sectors, test_case: SectorContentTestCase
):
    """
    Verifies the agent answers substantively using general knowledge when local RAG data
    does not cover the question, and applies hedging language instead of refusing.
    """
    logging.info("Running Career Explorer general-knowledge test case: %s", test_case.name)
    get_i18n_manager().set_locale(Locale.EN_US)

    executor = CareerExplorerExecutor()
    max_iterations = len(test_case.scripted_user) + 1

    conversation = await generate(
        max_iterations=max_iterations,
        execute_evaluated_agent=executor,
        execute_simulated_user=ScriptedSimulatedUser(script=test_case.scripted_user),
        is_finished=CareerExplorerIsFinished(),
    )

    _assert_rag_content(conversation, test_case)

    output_folder = os.path.join(
        os.getcwd(),
        "test_output",
        "career_explorer_agent",
        "general_knowledge",
        test_case.name,
    )
    os.makedirs(output_folder, exist_ok=True)

    from datetime import datetime, timezone
    time_now = datetime.now(timezone.utc).isoformat()
    base_name = f"{test_case.name}_{time_now}"

    from evaluation_tests.conversation_libs.evaluators.evaluation_result import ConversationEvaluationRecord
    record = ConversationEvaluationRecord(
        simulated_user_prompt=test_case.description,
        test_case=test_case.name,
    )
    record.add_conversation_records(conversation)
    record.save_data(folder=output_folder, base_file_name=base_name)

    context = await CareerExplorerGetConversationContextExecutor(executor)()
    ctx_path = os.path.join(output_folder, f"{base_name}_context")
    save_conversation_context_to_json(context=context, file_path=ctx_path + ".json")
    save_conversation_context_to_markdown(
        title=f"Career Explorer (General Knowledge): {test_case.name}",
        context=context,
        file_path=ctx_path + ".md",
    )
