import logging

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.server_dependencies.database_collections import Collections
from app.server_dependencies.db_dependencies import CompassDBProvider

logger = logging.getLogger(__name__)

# Demographic dimensions we can break down today, and the chart type each renders as.
# Add a dimension here once its underlying field is available.
_DIMENSIONS = [
    ("gender", "data.gender", "pie-chart"),
    ("region", "data.province", "horizontal-bar-chart"),
]


class DemographicsRepository:
    """Breaks registered users down by demographic fields stored in plain_personal_data."""

    def __init__(self, userdata_db: AsyncIOMotorDatabase):
        self._plain_data_collection = userdata_db.get_collection(Collections.PLAIN_PERSONAL_DATA)

    async def _breakdown(self, field: str, institution_names: list[str] | None) -> list[dict]:
        match: dict = {field: {"$exists": True, "$nin": [None, ""]}}
        if institution_names:
            match["data.institution_name"] = {"$in": institution_names}

        pipeline = [
            {"$match": match},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        results = await self._plain_data_collection.aggregate(pipeline).to_list(length=None)
        return [{"name": r["_id"], "value": r["count"]} for r in results]

    async def get_demographics(self, *, institution_names: list[str] | None = None) -> list[dict]:
        return [
            {"type": chart_type, "name": name, "items": await self._breakdown(field, institution_names)}
            for name, field, chart_type in _DIMENSIONS
        ]


async def get_demographics_repository(
    userdata_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_userdata_db),
) -> DemographicsRepository:
    return DemographicsRepository(userdata_db)
