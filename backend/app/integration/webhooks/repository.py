from datetime import datetime, timedelta
from typing import Mapping, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.integration.webhooks.types import WebhookDelivery, DeliveryStatus, WebhookEvent
from app.server_dependencies.database_collections import Collections
from common_libs.time_utilities import datetime_to_mongo_date, mongo_date_to_datetime


async def create_webhook_indexes(application_db: AsyncIOMotorDatabase) -> None:
    deliveries = application_db.get_collection(Collections.WEBHOOK_DELIVERIES)
    # the same thing is notified once: event_ref only has what identifies it, built the same way every time
    await deliveries.create_index([("event", 1), ("external_id", 1), ("event_ref", 1)], unique=True)
    # the retries look for the pending deliveries that are due
    await deliveries.create_index([("status", 1), ("next_attempt_at", 1)])


def _date(value: Optional[datetime]) -> Optional[datetime]:
    return datetime_to_mongo_date(value) if value is not None else None


class WebhookDeliveryRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._collection = db.get_collection(Collections.WEBHOOK_DELIVERIES)

    @staticmethod
    def _from_db_doc(doc: Mapping) -> WebhookDelivery:
        return WebhookDelivery(
            id=doc["_id"],
            event=WebhookEvent(doc["event"]),
            external_id=doc["external_id"],
            event_ref=doc["event_ref"],
            status=DeliveryStatus(doc["status"]),
            attempts=doc["attempts"],
            next_attempt_at=mongo_date_to_datetime(doc["next_attempt_at"]),
            lease_until=mongo_date_to_datetime(doc["lease_until"]),
            url=doc.get("url"),
            last_attempt_at=mongo_date_to_datetime(doc.get("last_attempt_at")),
            last_status_code=doc.get("last_status_code"),
            last_error=doc.get("last_error"),
            created_at=mongo_date_to_datetime(doc["created_at"]),
        )

    @staticmethod
    def _outcome_fields(delivery: WebhookDelivery) -> dict:
        return {
            "status": delivery.status.value,
            "attempts": delivery.attempts,
            "next_attempt_at": datetime_to_mongo_date(delivery.next_attempt_at),
            "lease_until": datetime_to_mongo_date(delivery.lease_until),
            "url": delivery.url,
            "last_attempt_at": _date(delivery.last_attempt_at),
            "last_status_code": delivery.last_status_code,
            "last_error": delivery.last_error,
        }

    async def insert(self, delivery: WebhookDelivery) -> bool:
        """
        :return: False if a delivery of the same event, user and event_ref exists (it was already notified)
        """
        try:
            await self._collection.insert_one({
                "_id": delivery.id,
                "event": delivery.event.value,
                "external_id": delivery.external_id,
                "event_ref": delivery.event_ref,
                "created_at": datetime_to_mongo_date(delivery.created_at),
                **self._outcome_fields(delivery),
            })
            return True
        except DuplicateKeyError:
            return False

    async def find_by_id(self, delivery_id: str) -> Optional[WebhookDelivery]:
        doc = await self._collection.find_one({"_id": {"$eq": delivery_id}})
        return self._from_db_doc(doc) if doc else None

    async def claim(self, now: datetime, lease: timedelta) -> Optional[WebhookDelivery]:
        """
        Hold the pending delivery due the longest that no other attempt holds, until now + lease. In one atomic
        update, so of several attempts claiming at the same time only one gets it.

        :return: the delivery claimed, or None if none is due
        """
        doc = await self._collection.find_one_and_update(
            {
                "status": {"$eq": DeliveryStatus.PENDING.value},
                "next_attempt_at": {"$lte": datetime_to_mongo_date(now)},
                "lease_until": {"$lte": datetime_to_mongo_date(now)},
            },
            {"$set": {"lease_until": datetime_to_mongo_date(now + lease)}},
            sort=[("next_attempt_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        return self._from_db_doc(doc) if doc else None

    async def save_outcome(self, delivery: WebhookDelivery) -> None:
        """
        Store the outcome of an attempt, by the attempt that holds the delivery.
        """
        await self._collection.update_one({"_id": {"$eq": delivery.id}}, {"$set": self._outcome_fields(delivery)})
