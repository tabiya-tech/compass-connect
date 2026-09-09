from abc import ABC, abstractmethod
import logging

from pymongo import InsertOne, UpdateOne

from app.metrics.types import AbstractCompassMetricEvent
from app.metrics.constants import EventType
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.server_dependencies.database_collections import Collections
from common_libs.time_utilities import datetime_to_mongo_date


class IMetricsRepository(ABC):
    @abstractmethod
    def record_event(self, event: list[AbstractCompassMetricEvent]):
        """
        Records a number of events in the repository.
        :param event: The event to record
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    async def get_sector_names_for_user(self, anonymized_user_id: str) -> list[str]:
        raise NotImplementedError()

    @abstractmethod
    async def get_aggregated_sector_engagement(self) -> list[dict]:
        raise NotImplementedError()

    @abstractmethod
    async def get_sector_engagement_for_user(self, anonymized_user_id: str) -> list[dict]:
        raise NotImplementedError()


class MetricsRepository(IMetricsRepository):
    def __init__(self, *, db: AsyncIOMotorDatabase):
        self.db = db
        self.logger = logging.getLogger(self.__class__.__name__)
        self.collection = db.get_collection(Collections.COMPASS_METRICS)

    @classmethod
    def _to_db_doc(cls, event: AbstractCompassMetricEvent) -> dict:
        event_dict = event.model_dump()
        
        # Ensure user_id is deleted with a warning if it exists
        if "user_id" in event_dict:
            logging.warning("user_id field found in event during repository processing. This should have been deleted in the service layer.")
            del event_dict["user_id"]

        if "session_id" in event_dict:
            logging.warning("session_id field found in event during repository processing. This should have been deleted in the service layer.")
            del event_dict["session_id"]
            
        event_dict["timestamp"] = datetime_to_mongo_date(event.timestamp)
        event_dict["event_type_name"] = event.event_type.name
        event_dict["event_type"] = event.event_type.value
        return event_dict

    async def record_event(self, events: list[AbstractCompassMetricEvent]):
        commands = []
        for event in events:
            match event.event_type:
                case EventType.FEEDBACK_PROVIDED:
                    #  There can only be one feedback provided event per session, if one already exists we should update it
                    commands.append(UpdateOne(
                        {
                            "event_type": {"$eq": EventType.FEEDBACK_PROVIDED.value},
                            "anonymized_user_id": {"$eq": event.anonymized_user_id},
                            "anonymized_session_id": {"$eq": event.anonymized_session_id}
                        },
                        {
                            "$set": self._to_db_doc(event)
                        },
                        upsert=True
                    ))
                case EventType.MESSAGE_REACTION_CREATED:
                    #  A message reaction can be updated multiple times, so we should upsert it
                    commands.append(UpdateOne(
                        {
                            "event_type": {"$eq": EventType.MESSAGE_REACTION_CREATED.value},
                            "anonymized_user_id": {"$eq": event.anonymized_user_id},
                            "anonymized_session_id": {"$eq": event.anonymized_session_id},
                            "message_id": {"$eq": event.message_id}
                        },
                        {
                            "$set": self._to_db_doc(event)
                        },
                        upsert=True
                    ))
                case EventType.CONVERSATION_TURN:
                    commands.append(UpdateOne(
                        {
                            "event_type": {"$eq": EventType.CONVERSATION_TURN.value},
                            "anonymized_user_id": {"$eq": event.anonymized_user_id},
                            "anonymized_session_id": {"$eq": event.anonymized_session_id},
                        },
                        # upsert the compass and user counts and increment the turn count (not in the passed event object)
                        {
                            "$set": self._to_db_doc(event),
                            "$inc": {"turn_count": 1}
                        },
                        upsert=True
                    ))
                case EventType.EXPERIENCE_DISCOVERED:
                    commands.append(UpdateOne(
                        {
                            "event_type": {"$eq": EventType.EXPERIENCE_DISCOVERED.value},
                            "anonymized_user_id": {"$eq": event.anonymized_user_id},
                            "anonymized_session_id": {"$eq": event.anonymized_session_id},
                        },
                        {"$set": self._to_db_doc(event)},
                        upsert=True
                    ))
                case EventType.EXPERIENCE_EXPLORED:
                    commands.append(UpdateOne(
                        {
                            "event_type": {"$eq": EventType.EXPERIENCE_EXPLORED.value},
                            "anonymized_user_id": {"$eq": event.anonymized_user_id},
                            "anonymized_session_id": {"$eq": event.anonymized_session_id},
                        },
                        {"$set": self._to_db_doc(event)},
                        upsert=True
                    ))
                case EventType.SECTOR_ENGAGEMENT:
                    commands.append(UpdateOne(
                        {
                            "event_type": {"$eq": EventType.SECTOR_ENGAGEMENT.value},
                            "anonymized_user_id": {"$eq": event.anonymized_user_id},
                            "sector_name": {"$eq": event.sector_name},
                        },
                        {
                            "$set": self._to_db_doc(event),
                            "$inc": {"inquiry_count": 1},
                        },
                        upsert=True,
                    ))
                case EventType.JOB_MATCHES_GENERATED:
                    #  One document per user — the endpoint re-runs matching on every visit, and
                    #  "profiles with matches" counts profiles, not matching runs.
                    commands.append(UpdateOne(
                        {
                            "event_type": {"$eq": EventType.JOB_MATCHES_GENERATED.value},
                            "anonymized_user_id": {"$eq": event.anonymized_user_id},
                        },
                        {
                            "$set": self._to_db_doc(event),
                            "$inc": {"match_generation_count": 1},
                        },
                        upsert=True,
                    ))
                case EventType.JOB_VIEWED:
                    #  One document per (user, job) — re-opening the same listing bumps the count
                    #  rather than adding a row, so "jobs viewed per user" counts distinct listings.
                    commands.append(UpdateOne(
                        {
                            "event_type": {"$eq": EventType.JOB_VIEWED.value},
                            "anonymized_user_id": {"$eq": event.anonymized_user_id},
                            "job_id": {"$eq": event.job_id},
                        },
                        {
                            "$set": self._to_db_doc(event),
                            "$inc": {"view_count": 1},
                        },
                        upsert=True,
                    ))
                case _:
                    commands.append(InsertOne(self._to_db_doc(event)))
        return await self.collection.bulk_write(commands)

    async def get_sector_names_for_user(self, anonymized_user_id: str) -> list[str]:
        return await self.collection.distinct(
            "sector_name",
            {
                "event_type": {"$eq": EventType.SECTOR_ENGAGEMENT.value},
                "anonymized_user_id": {"$eq": anonymized_user_id},
            },
        )

    async def get_aggregated_sector_engagement(self) -> list[dict]:
        pipeline = [
            {"$match": {"event_type": {"$eq": EventType.SECTOR_ENGAGEMENT.value}}},
            {"$group": {
                "_id": "$sector_name",
                "is_priority": {"$first": "$is_priority"},
                "total_inquiries": {"$sum": "$inquiry_count"},
                "unique_users": {"$addToSet": "$anonymized_user_id"},
            }},
            {"$project": {
                "_id": 0,
                "sector_name": "$_id",
                "is_priority": 1,
                "total_inquiries": 1,
                "unique_users": {"$size": "$unique_users"},
            }},
            {"$sort": {"total_inquiries": -1}},
        ]
        return await self.collection.aggregate(pipeline).to_list(length=None)

    async def get_sector_engagement_for_user(self, anonymized_user_id: str) -> list[dict]:
        cursor = self.collection.find(
            {
                "event_type": {"$eq": EventType.SECTOR_ENGAGEMENT.value},
                "anonymized_user_id": {"$eq": anonymized_user_id},
            },
            {
                "_id": 0,
                "sector_name": 1,
                "is_priority": 1,
                "inquiry_count": 1,
                "timestamp": 1,
            },
        ).sort("inquiry_count", -1)
        return await cursor.to_list(length=None)
