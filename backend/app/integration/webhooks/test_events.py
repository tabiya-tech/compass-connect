from datetime import datetime, timezone

import pytest

from app.integration.service import ExternalUserResultsResponse, ConversationResults
from app.integration.webhooks.events import ConversationCompleted, DataNotReadyError

_COMPLETED_AT = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)


def _results(*conversations: ConversationResults) -> ExternalUserResultsResponse:
    return ExternalUserResultsResponse(external_id="ext-1", email="person@example.com",
                                       conversations=list(conversations))


def _conversation(session_id: int, completed: bool) -> ConversationResults:
    return ConversationResults(session_id=session_id, conversation_completed=completed,
                               conversation_conducted_at=_COMPLETED_AT, experiences=[])


def _event_with_results(results: ExternalUserResultsResponse) -> ConversationCompleted:
    async def _get_results(external_id: str) -> ExternalUserResultsResponse:
        assert external_id == "ext-1"
        return results

    return ConversationCompleted(_get_results)


class TestConversationCompleted:
    def test_event_ref_is_the_session(self):
        # only what identifies the conversation: a new conversation (new session) is a new notification
        assert ConversationCompleted.event_ref(123) == {"session_id": 123}

    @pytest.mark.asyncio
    async def test_data_has_the_results_of_the_results_endpoint(self):
        # GIVEN the user's results, where the conversation is completed
        given_results = _results(_conversation(124, completed=False), _conversation(123, completed=True))

        # WHEN the data of the event is built
        actual = await _event_with_results(given_results).build_data("ext-1", ConversationCompleted.event_ref(123))

        # THEN it has the session, when it was completed, and the same results object, as JSON values
        assert actual == {"session_id": 123, "completed_at": "2026-10-28T10:00:00Z",
                          "results": given_results.model_dump(mode="json")}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_results", [
        _results(_conversation(123, completed=False)),
        _results(),
    ], ids=["reported as not completed (e.g. its state could not be read)", "not in the results"])
    async def test_not_ready_when_the_results_do_not_show_it_completed(self, given_results):
        # the webhook must not tell the platform "completed" with results that say otherwise: it is retried instead
        with pytest.raises(DataNotReadyError):
            await _event_with_results(given_results).build_data("ext-1", ConversationCompleted.event_ref(123))
