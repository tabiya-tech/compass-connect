from datetime import datetime
from typing import Mapping, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.integration.types import ExternalUser, HandoffLink, HandoffAction, Webhook
from app.server_dependencies.database_collections import Collections
from common_libs.time_utilities import datetime_to_mongo_date, mongo_date_to_datetime


class DuplicateExternalUserError(Exception):
    """
    Another user already has this external id or this email (e.g. a concurrent request created it first).
    """


async def create_integration_indexes(application_db: AsyncIOMotorDatabase) -> None:
    users = application_db.get_collection(Collections.EXTERNAL_USERS)
    await users.create_index([("external_id", 1)], unique=True)
    await users.create_index([("email", 1)], unique=True)
    # user_id and link are empty until the Firebase account exists and a link is issued: only set values are unique
    await users.create_index([("user_id", 1)], unique=True,
                             partialFilterExpression={"user_id": {"$type": "string"}})
    await users.create_index([("link.token_hash", 1)], unique=True,
                             partialFilterExpression={"link.token_hash": {"$type": "string"}})


class ExternalUserRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._collection = db.get_collection(Collections.EXTERNAL_USERS)

    @staticmethod
    def _from_db_doc(doc: Mapping) -> ExternalUser:
        link = doc.get("link")
        webhook = doc.get("webhook")
        return ExternalUser(
            external_id=doc["external_id"],
            email=doc["email"],
            user_id=doc.get("user_id"),
            link=HandoffLink(token_hash=link["token_hash"],
                             action=HandoffAction(link["action"]),
                             expires_at=mongo_date_to_datetime(link["expires_at"])) if link else None,
            webhook=Webhook(url=webhook["url"], secret=webhook["secret"]) if webhook else None,
            created_at=mongo_date_to_datetime(doc["created_at"]),
            updated_at=mongo_date_to_datetime(doc["updated_at"]),
        )

    async def find_by_external_id(self, external_id: str) -> Optional[ExternalUser]:
        doc = await self._collection.find_one({"external_id": {"$eq": external_id}})
        return self._from_db_doc(doc) if doc else None

    async def find_by_user_id(self, user_id: str) -> Optional[ExternalUser]:
        doc = await self._collection.find_one({"user_id": {"$eq": user_id}})
        return self._from_db_doc(doc) if doc else None

    async def find_by_email(self, email: str) -> Optional[ExternalUser]:
        doc = await self._collection.find_one({"email": {"$eq": email}})
        return self._from_db_doc(doc) if doc else None

    async def find_by_valid_link(self, token_hash: str, now: datetime) -> Optional[ExternalUser]:
        """
        The user whose link has this token hash, if the link has not expired.
        """
        doc = await self._collection.find_one({
            "link.token_hash": {"$eq": token_hash},
            "link.expires_at": {"$gt": datetime_to_mongo_date(now)},
        })
        return self._from_db_doc(doc) if doc else None

    async def insert(self, user: ExternalUser) -> None:
        """
        :raises DuplicateExternalUserError: if a user with the same external id or email exists
        """
        try:
            await self._collection.insert_one({
                "external_id": user.external_id,
                "email": user.email,
                "user_id": user.user_id,
                "link": None,
                "webhook": None,
                "created_at": datetime_to_mongo_date(user.created_at),
                "updated_at": datetime_to_mongo_date(user.updated_at),
            })
        except DuplicateKeyError as e:
            raise DuplicateExternalUserError() from e

    async def set_user_id(self, external_id: str, user_id: str, updated_at: datetime) -> None:
        await self._set(external_id, {"user_id": user_id, "updated_at": datetime_to_mongo_date(updated_at)})

    async def set_link(self, external_id: str, link: HandoffLink, updated_at: datetime) -> None:
        await self._set(external_id, {
            "link": {"token_hash": link.token_hash, "action": link.action.value,
                     "expires_at": datetime_to_mongo_date(link.expires_at)},
            "updated_at": datetime_to_mongo_date(updated_at),
        })

    async def set_webhook(self, external_id: str, webhook: Optional[Webhook], updated_at: datetime) -> None:
        """
        :param webhook: None removes it
        """
        await self._set(external_id, {
            "webhook": {"url": webhook.url, "secret": webhook.secret.get_secret_value()} if webhook else None,
            "updated_at": datetime_to_mongo_date(updated_at),
        })

    async def _set(self, external_id: str, fields: dict) -> None:
        result = await self._collection.update_one({"external_id": {"$eq": external_id}}, {"$set": fields})
        if result.matched_count == 0:
            raise ValueError(f"external user {external_id!r} not found")
