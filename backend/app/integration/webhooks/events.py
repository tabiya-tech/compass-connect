"""
What is specific to each webhook event: the `data` its notification carries. One subclass of WebhookEventDefinition
per event; everything else (storing, sending, retrying) is the same for all of them.

Adding an event: a WebhookEvent value, a subclass here, the subclass in the notifier's events, and a call to
WebhookNotifier.emit where the event happens.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Awaitable, Callable, ClassVar, Mapping, Optional

from pydantic import BaseModel

from app.integration.service import ExternalUserResultsResponse
from app.integration.webhooks.types import WebhookEvent


class DataNotReadyError(Exception):
    """
    The data of the event cannot be built correctly now. The attempt fails and is retried later.
    """


class WebhookEventDefinition(ABC):
    event: ClassVar[WebhookEvent]
    version: ClassVar[int]
    """
    The version of the shape of `data`. Bump it when `data` changes in a way that is not only additive.
    """

    @abstractmethod
    async def build_data(self, external_id: str, event_ref: Mapping[str, Any]) -> dict[str, Any]:
        """
        Build `data`, as JSON values, when an attempt is sent (so a retry carries the current data).

        :param event_ref: what `emit` was given. Only what identifies the event (e.g. the session id): a delivery is
                          unique per event, user and event_ref, so the same thing is notified once.
        :raises DataNotReadyError: to retry later
        """
        raise NotImplementedError()


class ConversationCompletedData(BaseModel):
    session_id: int
    completed_at: Optional[datetime]
    results: dict[str, Any]
    """
    The same object as GET /integration/users/{external_id}/results returns, as it is when the attempt is sent.
    """


class ConversationCompleted(WebhookEventDefinition):
    event = WebhookEvent.CONVERSATION_COMPLETED
    version = 1

    def __init__(self, get_results: Callable[[str], Awaitable[ExternalUserResultsResponse]]):
        """
        :param get_results: the results of an external user by external id (IntegrationService.get_results)
        """
        self._get_results = get_results

    @staticmethod
    def event_ref(session_id: int) -> dict[str, Any]:
        # a new conversation of the same user is a new session, so a new notification
        return {"session_id": session_id}

    async def build_data(self, external_id: str, event_ref: Mapping[str, Any]) -> dict[str, Any]:
        session_id = event_ref["session_id"]
        results = await self._get_results(external_id)
        conversation = next((c for c in results.conversations if c.session_id == session_id), None)
        if conversation is None or not conversation.conversation_completed:
            # the results report a conversation they could not read as not completed: send nothing wrong, retry
            raise DataNotReadyError(f"session {session_id} is not completed in the results")
        return ConversationCompletedData(session_id=session_id,
                                         completed_at=conversation.conversation_conducted_at,
                                         results=results.model_dump(mode="json")).model_dump(mode="json")
