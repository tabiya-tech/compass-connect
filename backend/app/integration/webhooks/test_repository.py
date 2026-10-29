from datetime import timedelta
from typing import Awaitable

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.integration.webhooks.repository import WebhookDeliveryRepository
from app.integration.webhooks.types import WebhookDelivery, WebhookEvent, DeliveryStatus
from common_libs.time_utilities import get_now, truncate_microseconds

_LEASE = timedelta(minutes=1)


@pytest.fixture(scope="function")
async def repository(in_memory_application_database: Awaitable[AsyncIOMotorDatabase]) -> WebhookDeliveryRepository:
    return WebhookDeliveryRepository(await in_memory_application_database)


def _delivery(delivery_id: str, *, session_id: int = 1, external_id: str = "ext-1",
              due_in: timedelta = timedelta(0), held_for: timedelta = timedelta(0),
              status: DeliveryStatus = DeliveryStatus.PENDING) -> WebhookDelivery:
    # MongoDB keeps milliseconds only
    now = truncate_microseconds(get_now())
    return WebhookDelivery(id=delivery_id, event=WebhookEvent.CONVERSATION_COMPLETED, external_id=external_id,
                           event_ref={"session_id": session_id}, status=status, next_attempt_at=now + due_in,
                           lease_until=now + held_for, created_at=now)


class TestWebhookDeliveryRepository:
    @pytest.mark.asyncio
    async def test_insert_and_find(self, repository: Awaitable[WebhookDeliveryRepository]):
        repository = await repository
        given = _delivery("d-1")
        assert await repository.insert(given) is True
        assert await repository.find_by_id("d-1") == given

    @pytest.mark.asyncio
    async def test_same_event_user_and_ref_is_inserted_once(self, repository: Awaitable[WebhookDeliveryRepository]):
        repository = await repository
        await repository.insert(_delivery("d-1", session_id=1))

        assert await repository.insert(_delivery("d-2", session_id=1)) is False
        assert await repository.insert(_delivery("d-3", session_id=2)) is True
        assert await repository.insert(_delivery("d-4", session_id=1, external_id="ext-2")) is True
        assert await repository.find_by_id("d-2") is None

    @pytest.mark.asyncio
    async def test_claim_takes_pending_due_and_free_deliveries_oldest_first(
            self, repository: Awaitable[WebhookDeliveryRepository]):
        repository = await repository
        # GIVEN deliveries that cannot be attempted now, and two that can
        await repository.insert(_delivery("not-due", session_id=1, due_in=timedelta(minutes=5)))
        await repository.insert(_delivery("held", session_id=2, held_for=timedelta(minutes=5)))
        await repository.insert(_delivery("delivered", session_id=3, status=DeliveryStatus.DELIVERED))
        await repository.insert(_delivery("failed", session_id=4, status=DeliveryStatus.FAILED))
        await repository.insert(_delivery("due-recently", session_id=5, due_in=timedelta(seconds=-1)))
        await repository.insert(_delivery("due-long-ago", session_id=6, due_in=timedelta(seconds=-10)))

        # WHEN deliveries are claimed until none is left
        now = get_now()
        actual = []
        while (claimed := await repository.claim(now, _LEASE)) is not None:
            actual.append(claimed)

        # THEN only the two due ones are claimed, the one due the longest first, each held for the lease
        assert [delivery.id for delivery in actual] == ["due-long-ago", "due-recently"]
        assert all(delivery.lease_until == truncate_microseconds(now + _LEASE) for delivery in actual)

    @pytest.mark.asyncio
    async def test_save_outcome(self, repository: Awaitable[WebhookDeliveryRepository]):
        repository = await repository
        await repository.insert(_delivery("d-1"))
        now = truncate_microseconds(get_now())
        given = (await repository.find_by_id("d-1")).model_copy(update={
            "status": DeliveryStatus.DELIVERED, "attempts": 2, "url": "https://api.partner.example.org/hook",
            "last_attempt_at": now, "last_status_code": 204, "lease_until": now})

        await repository.save_outcome(given)

        assert await repository.find_by_id("d-1") == given
