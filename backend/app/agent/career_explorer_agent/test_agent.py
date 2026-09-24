"""
Tests for how the CareerExplorerAgent reports the sector classifier's verdict on the turn's trace.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.agent_types import AgentInput
from app.agent.career_explorer_agent.agent import CareerExplorerAgent
from app.agent.career_explorer_agent.sector_relevance_classifier import SectorClassificationResult, SectorRelevance
from app.observability.module_types import TraceModule, TraceSubModule
from common_libs.observability.testing import in_memory_tracing
from common_libs.observability.tracing import start_trace


def _a_classification(relevance: SectorRelevance, *, failed: bool = False) -> SectorClassificationResult:
    is_priority = relevance == SectorRelevance.PRIORITY_SECTOR
    return SectorClassificationResult(
        relevance=relevance,
        sector_name=None if failed else ("Mining" if is_priority else "Healthcare"),
        is_priority=is_priority,
        reasoning="",
        llm_stats=[],
        all_sectors=[],
        classification_failed=failed,
    )


def _an_agent(classification: SectorClassificationResult) -> CareerExplorerAgent:
    """A CareerExplorerAgent whose classifier and explorers are stubbed out."""
    agent = CareerExplorerAgent(sector_search_service=MagicMock())
    explored = ("a reply", False, "", [], None)
    agent._classifier = MagicMock()  # pylint: disable=protected-access
    agent._classifier.classify = AsyncMock(return_value=classification)  # pylint: disable=protected-access
    agent._priority_explorer = MagicMock()  # pylint: disable=protected-access
    agent._priority_explorer.explore = AsyncMock(return_value=explored)  # pylint: disable=protected-access
    agent._non_priority_explorer = MagicMock()  # pylint: disable=protected-access
    agent._non_priority_explorer.explore = AsyncMock(return_value=explored)  # pylint: disable=protected-access
    return agent


async def _run_a_turn(agent: CareerExplorerAgent, recorded_spans, record_score: MagicMock | None = None):
    """
    Run one turn inside a Career Explorer trace and return its root span.

    Scores are exported through their own ingestion queue rather than the span exporter, so the
    in-memory test client would block flushing one to its fake host; `record_score` is stubbed.
    """
    context = MagicMock()
    context.all_history.turns = []
    with patch("app.agent.career_explorer_agent.agent.get_application_config") as config, \
            patch("app.agent.career_explorer_agent.agent.record_score", record_score or MagicMock()):
        config.return_value.career_explorer_config.priority_nudge_every_n_turns = 0
        with start_trace(name="career_explorer.turn", module=TraceModule.CAREER_EXPLORER.value):
            await agent.execute(AgentInput(message="what jobs are there?"), context)
    return recorded_spans.by_name("career_explorer.turn")


class TestSectorClassificationAttribution:
    """
    Tests for reporting the sector classifier's verdict as the Career Explorer sub module.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_relevance, expected_sub_module", [
        (SectorRelevance.PRIORITY_SECTOR, TraceSubModule.PRIORITY_SECTOR.value),
        (SectorRelevance.NON_PRIORITY_SECTOR, TraceSubModule.NON_PRIORITY_SECTOR.value),
    ], ids=["priority", "non-priority"])
    async def test_reports_the_verdict_as_the_sub_module(self, given_relevance, expected_sub_module):
        """Reports the verdict as the sub module."""
        # GIVEN the classifier gives a verdict
        given_agent = _an_agent(_a_classification(given_relevance))

        # WHEN a turn is handled
        actual_record_score = MagicMock()
        with in_memory_tracing() as recorded_spans:
            actual_span = await _run_a_turn(given_agent, recorded_spans, actual_record_score)

        # THEN expect the verdict to be tagged as the sub module
        actual_tags = actual_span.attributes["langfuse.trace.tags"]
        assert f"sub_module:{expected_sub_module}" in actual_tags
        assert actual_span.attributes["langfuse.trace.metadata.sub_module"] == expected_sub_module
        # AND expect no classifier failure to be reported
        assert "sector_classifier:failed" not in actual_tags
        actual_record_score.assert_not_called()

    @pytest.mark.asyncio
    async def test_reports_a_failed_classification_apart_from_the_non_priority_fallback(self):
        """Reports a failed classification apart from the non-priority fallback."""
        # GIVEN the classifier fails and falls back to non-priority
        given_agent = _an_agent(_a_classification(SectorRelevance.NON_PRIORITY_SECTOR, failed=True))

        # WHEN a turn is handled
        actual_record_score = MagicMock()
        with in_memory_tracing() as recorded_spans:
            actual_span = await _run_a_turn(given_agent, recorded_spans, actual_record_score)

        # THEN expect the turn to be reported as a classifier failure, not as a non-priority turn
        actual_tags = actual_span.attributes["langfuse.trace.tags"]
        assert f"sub_module:{TraceSubModule.SECTOR_CLASSIFIER_FAILED.value}" in actual_tags
        assert f"sub_module:{TraceSubModule.NON_PRIORITY_SECTOR.value}" not in actual_tags
        # AND expect it to be tagged as a failure, so failures can be filtered on directly
        assert "sector_classifier:failed" in actual_tags
        # AND expect the fallback it took to be recorded
        assert actual_span.attributes["langfuse.trace.metadata.sector_classifier_fallback"] == TraceSubModule.NON_PRIORITY_SECTOR.value
        # AND expect the failure to be scored, so it can be charted over time
        actual_record_score.assert_called_once()
        assert actual_record_score.call_args.kwargs["name"] == "sector_classifier_failed"
        # AND expect the turn to still be answered by the non-priority explorer
        given_agent._non_priority_explorer.explore.assert_awaited_once()  # pylint: disable=protected-access
