"""
Tests for the reach analytics repository (composition of stats + adoption trends).
"""
import hashlib
from datetime import datetime, timezone
from typing import Awaitable

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.analytics.reach.repository import ReachRepository
from app.metrics.constants import EventType
from app.server_dependencies.database_collections import Collections
from common_libs.time_utilities import datetime_to_mongo_date


def _anon(user_id: str) -> str:
    return hashlib.md5(user_id.encode(), usedforsecurity=False).hexdigest()


def _account_created(user_id: str, ts: datetime) -> dict:
    return {
        "event_type": EventType.USER_ACCOUNT_CREATED.value,
        "anonymized_user_id": _anon(user_id),
        "timestamp": datetime_to_mongo_date(ts),
    }


def _generic_event(user_id: str, ts: datetime) -> dict:
    return {
        "event_type": EventType.CONVERSATION_PHASE.value,
        "anonymized_user_id": _anon(user_id),
        "timestamp": datetime_to_mongo_date(ts),
    }


@pytest.fixture(scope="function")
async def populated_repository(
    in_memory_application_database: Awaitable[AsyncIOMotorDatabase],
    in_memory_userdata_database: Awaitable[AsyncIOMotorDatabase],
    in_memory_metrics_database: Awaitable[AsyncIOMotorDatabase],
) -> ReachRepository:
    """
    Data layout:
      - 3 registered students (user_preferences): user-a, user-b, user-c
      - user-a, user-b belong to "Test School" (plain_personal_data)
      - USER_ACCOUNT_CREATED: user-a on Jan 1, user-b on Jan 2 (2 new registrations in range)
      - generic activity: user-a and user-c active recently (for DAU / active_30d)
    """
    app_db = await in_memory_application_database
    userdata_db = await in_memory_userdata_database
    metrics_db = await in_memory_metrics_database

    await app_db.get_collection(Collections.USER_PREFERENCES).insert_many([
        {"user_id": "user-a"}, {"user_id": "user-b"}, {"user_id": "user-c"},
    ])
    await userdata_db.get_collection(Collections.PLAIN_PERSONAL_DATA).insert_many([
        {"user_id": "user-a", "data": {"institution_name": "Test School"}},
        {"user_id": "user-b", "data": {"institution_name": "Test School"}},
        {"user_id": "user-c", "data": {"institution_name": "Other School"}},
    ])

    now = datetime.now(tz=timezone.utc)
    jan1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    jan2 = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    await metrics_db.get_collection(Collections.COMPASS_METRICS).insert_many([
        _account_created("user-a", jan1),
        _account_created("user-b", jan2),
        # Recent activity (within 30 days) — user-a and user-c active
        _generic_event("user-a", now),
        _generic_event("user-c", now),
    ])

    return ReachRepository(app_db, userdata_db, metrics_db)


_JAN1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
_JAN3 = datetime(2026, 1, 3, 23, 59, tzinfo=timezone.utc)


class TestGetReach:
    @pytest.mark.asyncio
    async def test_summary_counts_all_users_and_recent_active(
        self, populated_repository: Awaitable[ReachRepository]
    ):
        repo = await populated_repository
        result = await repo.get_reach(start_date=_JAN1, end_date=_JAN3)

        # THEN total_users counts all user_preferences docs
        assert result["summary"]["total_users"] == 3
        # AND active_users_30d counts distinct anon users active in last 30d (user-a, user-c)
        assert result["summary"]["active_users_30d"] == 2

    @pytest.mark.asyncio
    async def test_series_maps_registrations_and_accumulates(
        self, populated_repository: Awaitable[ReachRepository]
    ):
        repo = await populated_repository
        result = await repo.get_reach(start_date=_JAN1, end_date=_JAN3)

        series = result["series"]
        # THEN there is one point per day in range (Jan 1, 2, 3)
        assert [p["label"] for p in series] == ["2026-01-01", "2026-01-02", "2026-01-03"]
        # AND new_users maps from registrations per day
        assert [p["new_users"] for p in series] == [1, 1, 0]
        # AND cumulative is the running sum of registrations
        assert [p["cumulative"] for p in series] == [1, 2, 2]

    @pytest.mark.asyncio
    async def test_login_fields_are_zero_documented_gap(
        self, populated_repository: Awaitable[ReachRepository]
    ):
        repo = await populated_repository
        result = await repo.get_reach(start_date=_JAN1, end_date=_JAN3)

        # THEN login/session fields are zero — Compass records no such events
        assert result["summary"]["total_logins"] == 0
        assert result["summary"]["avg_logins_per_user"] == 0.0
        assert result["summary"]["avg_session_minutes"] == 0
        assert all(p["logins"] == 0 for p in result["series"])

    @pytest.mark.asyncio
    async def test_institution_scope_limits_totals(
        self, populated_repository: Awaitable[ReachRepository]
    ):
        repo = await populated_repository
        result = await repo.get_reach(
            start_date=_JAN1, end_date=_JAN3, institution_name="Test School"
        )

        # THEN total_users counts only Test School students (user-a, user-b)
        assert result["summary"]["total_users"] == 2
        # AND active_users_30d counts only Test School active users (user-a)
        assert result["summary"]["active_users_30d"] == 1
