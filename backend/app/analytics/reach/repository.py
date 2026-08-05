import hashlib
import logging
from datetime import datetime, timedelta, timezone

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.analytics.adoption_trends.repository import AdoptionTrendsRepository
from app.analytics.stats.repository import DashboardStatsRepository
from app.server_dependencies.database_collections import Collections
from app.server_dependencies.db_dependencies import CompassDBProvider
from common_libs.time_utilities import datetime_to_mongo_date

logger = logging.getLogger(__name__)

PLAIN_DATA_SCHOOL_KEY = "institution_name"


def _anonymize(user_id: str) -> str:
    return hashlib.md5(user_id.encode(), usedforsecurity=False).hexdigest()


class ReachRepository:
    """
    Composes the existing dashboard stats and adoption trends repositories into
    the reach summary + series that the compass-analytics dashboard consumes.

    Data limitations (Compass records no login or session-duration events):
      - total_logins, avg_logins_per_user, avg_session_minutes and the per-point
        `logins` are always 0. Daily active users is used as the closest proxy
        for `returning`.
    """

    def __init__(
        self,
        application_db: AsyncIOMotorDatabase,
        userdata_db: AsyncIOMotorDatabase,
        metrics_db: AsyncIOMotorDatabase,
    ):
        self._stats = DashboardStatsRepository(application_db, userdata_db, metrics_db)
        self._adoption = AdoptionTrendsRepository(metrics_db)
        self._prefs_collection = application_db.get_collection(Collections.USER_PREFERENCES)
        self._plain_data_collection = userdata_db.get_collection(Collections.PLAIN_PERSONAL_DATA)
        self._metrics_collection = metrics_db.get_collection(Collections.COMPASS_METRICS)

    async def _count_active_users_last_n_days(self, days: int, institution_name: str | None = None) -> int:
        """Count distinct users with any metric event in the last `days`, optionally scoped to an institution."""
        now = datetime.now(tz=timezone.utc)
        start_mongo = datetime_to_mongo_date(now - timedelta(days=days))

        match: dict = {"timestamp": {"$gte": start_mongo}}
        if institution_name is not None:
            ppd = await self._plain_data_collection.find(
                {f"data.{PLAIN_DATA_SCHOOL_KEY}": institution_name}, {"user_id": 1}
            ).to_list(length=None)
            user_ids = [d["user_id"] for d in ppd if d.get("user_id")]
            if not user_ids:
                return 0
            match["anonymized_user_id"] = {"$in": [_anonymize(uid) for uid in user_ids]}
        else:
            match["anonymized_user_id"] = {"$exists": True, "$ne": None}

        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$anonymized_user_id"}},
            {"$count": "total"},
        ]
        result = await self._metrics_collection.aggregate(pipeline).to_list(length=1)
        return result[0]["total"] if result else 0

    async def get_reach(
        self,
        *,
        start_date: datetime,
        end_date: datetime,
        institution_name: str | None = None,
    ) -> dict:
        total_users = await self._stats.count_total_users(institution_name)
        active_users_30d = await self._count_active_users_last_n_days(30, institution_name)

        raw_series = await self._adoption.get_adoption_trends(
            start_date=start_date,
            end_date=end_date,
            interval="day",
        )

        series: list[dict] = []
        cumulative = 0
        for point in raw_series:
            added = point["new_registrations"]
            cumulative += added
            series.append({
                "label": point["date"],
                "cumulative": cumulative,
                "added": added,
                "new_users": added,
                "returning": point["daily_active_users"],
                # No login events exist in Compass; see class docstring.
                "logins": 0,
            })

        return {
            "summary": {
                "total_users": total_users,
                "active_users_30d": active_users_30d,
                "total_logins": 0,
                "avg_logins_per_user": 0.0,
                "avg_session_minutes": 0,
            },
            "series": series,
        }


async def get_reach_repository(
    application_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_application_db),
    userdata_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_userdata_db),
    metrics_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_metrics_db),
) -> ReachRepository:
    return ReachRepository(application_db, userdata_db, metrics_db)
