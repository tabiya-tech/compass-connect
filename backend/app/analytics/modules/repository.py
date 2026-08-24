import hashlib
import logging
import statistics
from datetime import datetime, timedelta

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.analytics.stats.repository import DashboardStatsRepository
from app.metrics.constants import EventType
from app.server_dependencies.database_collections import Collections
from app.server_dependencies.db_dependencies import CompassDBProvider
from common_libs.time_utilities import datetime_to_mongo_date

logger = logging.getLogger(__name__)

PLAIN_DATA_SCHOOL_KEY = "institution_name"

_EXPERIENCES_OR_LATER = ["COLLECT_EXPERIENCES", "DIVE_IN", "CHECKOUT", "ENDED"]
_SKILLS_OR_LATER = ["DIVE_IN", "CHECKOUT", "ENDED"]

# A full day — the cutoff between "same sitting" and "resumed later"
_MAX_REALISTIC_COMPLETION_MINUTES = 24 * 60

_DATE_FORMAT_BY_GRANULARITY = {
    "day": "%Y-%m-%d",
    "week": "%G-W%V",  # ISO week-year + week number
    "month": "%Y-%m",
}


def _anonymize(user_id: str) -> str:
    return hashlib.md5(user_id.encode(), usedforsecurity=False).hexdigest()


def _bucket_labels(start_date: datetime, end_date: datetime, granularity: str) -> list[str]:
    """Generate every bucket label in [start_date, end_date], so buckets with no events still appear as zeros."""
    labels: list[str] = []
    if granularity == "day":
        current = start_date
        while current <= end_date:
            labels.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
    elif granularity == "week":
        current = start_date - timedelta(days=start_date.weekday())  # align to Monday
        seen: set[str] = set()
        while current <= end_date:
            iso_year, iso_week, _ = current.isocalendar()
            label = f"{iso_year}-W{iso_week:02d}"
            if label not in seen:
                seen.add(label)
                labels.append(label)
            current += timedelta(days=7)
    else:  # month
        current = start_date.replace(day=1)
        while current <= end_date:
            labels.append(current.strftime("%Y-%m"))
            current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return labels


class ModuleAnalyticsRepository:
    """
    Build Your Profile adoption summary and time series, aggregated from metric_events:
    started/completed come from ConversationPhaseEvent, downloads from CV_DOWNLOADED.
    """

    def __init__(
        self,
        application_db: AsyncIOMotorDatabase,
        userdata_db: AsyncIOMotorDatabase,
        metrics_db: AsyncIOMotorDatabase,
    ):
        self._stats = DashboardStatsRepository(application_db, userdata_db, metrics_db)
        self._plain_data_collection = userdata_db.get_collection(Collections.PLAIN_PERSONAL_DATA)
        self._metrics_collection = metrics_db.get_collection(Collections.COMPASS_METRICS)

    async def _resolve_user_ids(self, institution_names: list[str]) -> list[str]:
        ppd = await self._plain_data_collection.find(
            {f"data.{PLAIN_DATA_SCHOOL_KEY}": {"$in": institution_names}}, {"user_id": 1}
        ).to_list(length=None)
        return [d["user_id"] for d in ppd if d.get("user_id")]

    async def _count_total_users(self, institution_names: list[str] | None) -> int:
        if not institution_names:
            return await self._stats.count_total_users(None)
        return sum([await self._stats.count_total_users(name) for name in institution_names])

    @staticmethod
    def _empty_response(labels: list[str]) -> dict:
        return {
            "summary": {
                "started_users": 0,
                "started_percentage": 0.0,
                "completed_users": 0,
                "avg_completion_minutes": 0.0,
            },
            "series": [
                {"label": label, "started": 0, "completed": 0, "skills_reports_generated": 0, "skills_reports_downloaded": 0}
                for label in labels
            ],
            "phases": [
                {"id": "intro", "reached": 0},
                {"id": "experiences", "reached": 0},
                {"id": "skills", "reached": 0},
                {"id": "completed", "reached": 0},
            ],
        }

    async def get_build_your_profile(
        self,
        *,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "day",
        institution_names: list[str] | None = None,
    ) -> dict:
        labels = _bucket_labels(start_date, end_date, granularity)

        anon_filter = None
        if institution_names:
            user_ids = await self._resolve_user_ids(institution_names)
            if not user_ids:
                return self._empty_response(labels)
            anon_filter = {"$in": [_anonymize(uid) for uid in user_ids]}

        total_users = await self._count_total_users(institution_names)

        date_format = _DATE_FORMAT_BY_GRANULARITY[granularity]
        start_mongo = datetime_to_mongo_date(start_date)
        end_mongo = datetime_to_mongo_date(end_date)

        phase_match: dict = {
            "timestamp": {"$gte": start_mongo, "$lte": end_mongo},
            "event_type": EventType.CONVERSATION_PHASE.value,
        }
        if anon_filter is not None:
            phase_match["anonymized_user_id"] = anon_filter
        ended_match = {**phase_match, "phase": "ENDED"}

        download_match: dict = {
            "timestamp": {"$gte": start_mongo, "$lte": end_mongo},
            "event_type": EventType.CV_DOWNLOADED.value,
        }
        if anon_filter is not None:
            download_match["anonymized_user_id"] = anon_filter

        started_by_bucket = await self._distinct_users_per_bucket(phase_match, date_format)
        completed_by_bucket = await self._count_per_bucket(ended_match, date_format)
        downloads_by_bucket = await self._count_per_bucket(download_match, date_format)

        series = [
            {
                "label": label,
                "started": started_by_bucket.get(label, 0),
                "completed": completed_by_bucket.get(label, 0),
                "skills_reports_generated": completed_by_bucket.get(label, 0),
                "skills_reports_downloaded": downloads_by_bucket.get(label, 0),
            }
            for label in labels
        ]

        started_users = await self._count_distinct_users(phase_match)
        completed_users = await self._count_distinct_users(ended_match)
        reached_experiences = await self._count_distinct_users({**phase_match, "phase": {"$in": _EXPERIENCES_OR_LATER}})
        reached_skills = await self._count_distinct_users({**phase_match, "phase": {"$in": _SKILLS_OR_LATER}})
        avg_minutes = await self._completion_minutes(phase_match)

        return {
            "summary": {
                "started_users": started_users,
                "started_percentage": (started_users / total_users * 100) if total_users else 0.0,
                "completed_users": completed_users,
                "avg_completion_minutes": avg_minutes,
            },
            "series": series,
            "phases": [
                {"id": "intro", "reached": started_users},
                {"id": "experiences", "reached": reached_experiences},
                {"id": "skills", "reached": reached_skills},
                {"id": "completed", "reached": completed_users},
            ],
        }

    async def _count_per_bucket(self, match: dict, date_format: str) -> dict[str, int]:
        pipeline = [
            {"$match": match},
            {"$addFields": {"date_str": {"$dateToString": {"format": date_format, "date": "$timestamp"}}}},
            {"$group": {"_id": "$date_str", "count": {"$sum": 1}}},
        ]
        results = await self._metrics_collection.aggregate(pipeline).to_list(length=None)
        return {r["_id"]: r["count"] for r in results}

    async def _distinct_users_per_bucket(self, match: dict, date_format: str) -> dict[str, int]:
        pipeline = [
            {"$match": match},
            {"$addFields": {"date_str": {"$dateToString": {"format": date_format, "date": "$timestamp"}}}},
            {"$group": {"_id": "$date_str", "users": {"$addToSet": "$anonymized_user_id"}}},
            {"$project": {"_id": 1, "count": {"$size": "$users"}}},
        ]
        results = await self._metrics_collection.aggregate(pipeline).to_list(length=None)
        return {r["_id"]: r["count"] for r in results}

    async def _count_distinct_users(self, match: dict) -> int:
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$anonymized_user_id"}},
            {"$count": "total"},
        ]
        result = await self._metrics_collection.aggregate(pipeline).to_list(length=1)
        return result[0]["total"] if result else 0

    async def _completion_minutes(self, phase_match: dict) -> float:
        """
        Per anonymized_session_id: minutes from the first phase event to the ENDED event, for
        sessions completed within a day — see _MAX_REALISTIC_COMPLETION_MINUTES. completed_users
        counts every ENDED session regardless; only this average excludes the longer outliers.
        """
        pipeline = [
            {"$match": phase_match},
            {
                "$group": {
                    "_id": "$anonymized_session_id",
                    "first_ts": {"$min": "$timestamp"},
                    "ended_ts": {"$max": {"$cond": [{"$eq": ["$phase", "ENDED"]}, "$timestamp", None]}},
                }
            },
            {"$match": {"ended_ts": {"$ne": None}}},
            {"$project": {"duration_minutes": {"$divide": [{"$subtract": ["$ended_ts", "$first_ts"]}, 60000]}}},
            {"$match": {"duration_minutes": {"$lte": _MAX_REALISTIC_COMPLETION_MINUTES}}},
        ]
        results = await self._metrics_collection.aggregate(pipeline).to_list(length=None)
        durations = [r["duration_minutes"] for r in results]
        return statistics.mean(durations) if durations else 0.0


async def get_module_analytics_repository(
    application_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_application_db),
    userdata_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_userdata_db),
    metrics_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_metrics_db),
) -> ModuleAnalyticsRepository:
    return ModuleAnalyticsRepository(application_db, userdata_db, metrics_db)
