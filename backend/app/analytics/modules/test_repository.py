import hashlib
from datetime import datetime, timedelta, timezone
from typing import Awaitable

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.analytics.modules.repository import CareerExplorerModuleRepository, ModuleAnalyticsRepository
from app.metrics.constants import EventType
from app.server_dependencies.database_collections import Collections
from common_libs.time_utilities import datetime_to_mongo_date


def _anon(value: str) -> str:
    return hashlib.md5(value.encode(), usedforsecurity=False).hexdigest()


def _phase_event(user_id: str, session_id: int, phase: str, ts: datetime) -> dict:
    return {
        "event_type": EventType.CONVERSATION_PHASE.value,
        "anonymized_user_id": _anon(user_id),
        "anonymized_session_id": _anon(str(session_id)),
        "phase": phase,
        "timestamp": datetime_to_mongo_date(ts),
    }


def _download_event(user_id: str, ts: datetime) -> dict:
    return {
        "event_type": EventType.CV_DOWNLOADED.value,
        "anonymized_user_id": _anon(user_id),
        "timestamp": datetime_to_mongo_date(ts),
    }


@pytest.fixture(scope="function")
async def populated_repository(
    in_memory_application_database: Awaitable[AsyncIOMotorDatabase],
    in_memory_userdata_database: Awaitable[AsyncIOMotorDatabase],
    in_memory_metrics_database: Awaitable[AsyncIOMotorDatabase],
) -> ModuleAnalyticsRepository:
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

    jan1_start = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    jan1_end = datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
    jan2_start = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)

    await metrics_db.get_collection(Collections.COMPASS_METRICS).insert_many([
        _phase_event("user-a", 1001, "INTRO", jan1_start),
        _phase_event("user-a", 1001, "ENDED", jan1_end),
        _download_event("user-a", jan1_end),
        _phase_event("user-b", 1002, "INTRO", jan2_start),
        _phase_event("user-c", 2001, "INTRO", jan1_start),
        _phase_event("user-c", 2001, "ENDED", jan1_end),
    ])

    return ModuleAnalyticsRepository(app_db, userdata_db, metrics_db)


_JAN1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
_JAN3 = datetime(2026, 1, 3, 23, 59, tzinfo=timezone.utc)


class TestGetBuildYourProfile:
    @pytest.mark.asyncio
    async def test_summary_counts_started_and_completed_across_all_institutions(
        self, populated_repository: Awaitable[ModuleAnalyticsRepository]
    ):
        repo = await populated_repository
        result = await repo.get_build_your_profile(start_date=_JAN1, end_date=_JAN3, granularity="day")

        # THEN started_users counts everyone with a phase event (user-a, user-b, user-c)
        assert result["summary"]["started_users"] == 3
        # AND completed_users counts only those with an ENDED event (user-a, user-c)
        assert result["summary"]["completed_users"] == 2
        # AND percentages are against total registered users (3)
        assert result["summary"]["started_percentage"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_series_still_reports_skills_report_counts_per_bucket(
        self, populated_repository: Awaitable[ModuleAnalyticsRepository]
    ):
        repo = await populated_repository
        result = await repo.get_build_your_profile(start_date=_JAN1, end_date=_JAN3, granularity="day")

        # THEN Jan 1's bucket proxies skills reports from that day's ENDED and CV_DOWNLOADED events
        jan1 = next(p for p in result["series"] if p["label"] == "2026-01-01")
        assert jan1["skills_reports_generated"] == 2  # user-a, user-c both ended that day
        assert jan1["skills_reports_downloaded"] == 1  # user-a's download

    @pytest.mark.asyncio
    async def test_completion_time_is_measured_per_session(
        self, populated_repository: Awaitable[ModuleAnalyticsRepository]
    ):
        repo = await populated_repository
        result = await repo.get_build_your_profile(start_date=_JAN1, end_date=_JAN3, granularity="day")

        # THEN both completed sessions took 30 minutes (user-b's in-progress session is excluded)
        assert result["summary"]["avg_completion_minutes"] == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_series_has_one_point_per_day_with_zero_filled_gaps(
        self, populated_repository: Awaitable[ModuleAnalyticsRepository]
    ):
        repo = await populated_repository
        result = await repo.get_build_your_profile(start_date=_JAN1, end_date=_JAN3, granularity="day")

        series = result["series"]
        assert [p["label"] for p in series] == ["2026-01-01", "2026-01-02", "2026-01-03"]
        # Jan 1: user-a and user-c started and completed; Jan 2: user-b started only; Jan 3: nothing
        assert [p["started"] for p in series] == [2, 1, 0]
        assert [p["completed"] for p in series] == [2, 0, 0]

    @pytest.mark.asyncio
    async def test_institution_scope_limits_totals_and_completion_time(
        self, populated_repository: Awaitable[ModuleAnalyticsRepository]
    ):
        repo = await populated_repository
        result = await repo.get_build_your_profile(
            start_date=_JAN1, end_date=_JAN3, granularity="day", institution_names=["Test School"]
        )

        # THEN only Test School's users (user-a, user-b) are counted
        assert result["summary"]["started_users"] == 2
        assert result["summary"]["completed_users"] == 1
        # AND completion time reflects only user-a's 30-minute session (user-c is scoped out)
        assert result["summary"]["avg_completion_minutes"] == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_institution_scope_with_no_matching_users_returns_empty(
        self, populated_repository: Awaitable[ModuleAnalyticsRepository]
    ):
        repo = await populated_repository
        result = await repo.get_build_your_profile(
            start_date=_JAN1, end_date=_JAN3, granularity="day", institution_names=["Nonexistent School"]
        )

        assert result["summary"]["started_users"] == 0
        assert result["summary"]["completed_users"] == 0
        assert all(p["started"] == 0 and p["completed"] == 0 for p in result["series"])
        assert all(stage["reached"] == 0 for stage in result["phases"])


@pytest.fixture(scope="function")
async def resumed_session_repository(
    in_memory_application_database: Awaitable[AsyncIOMotorDatabase],
    in_memory_userdata_database: Awaitable[AsyncIOMotorDatabase],
    in_memory_metrics_database: Awaitable[AsyncIOMotorDatabase],
) -> ModuleAnalyticsRepository:
    """user-normal: 20 minutes. user-long-day: 10 hours, same day. user-resumed: idle 3 days before finishing."""
    app_db = await in_memory_application_database
    metrics_db = await in_memory_metrics_database

    await app_db.get_collection(Collections.USER_PREFERENCES).insert_many([
        {"user_id": "user-normal"}, {"user_id": "user-long-day"}, {"user_id": "user-resumed"},
    ])

    start = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    await metrics_db.get_collection(Collections.COMPASS_METRICS).insert_many([
        _phase_event("user-normal", 1, "INTRO", start),
        _phase_event("user-normal", 1, "ENDED", start + timedelta(minutes=20)),
        _phase_event("user-long-day", 2, "INTRO", start),
        _phase_event("user-long-day", 2, "ENDED", start + timedelta(hours=10)),
        _phase_event("user-resumed", 3, "INTRO", start),
        _phase_event("user-resumed", 3, "ENDED", start + timedelta(days=3)),
    ])

    return ModuleAnalyticsRepository(app_db, await in_memory_userdata_database, metrics_db)


class TestCompletionTimeExcludesSessionsResumedADayOrMoreLater:
    @pytest.mark.asyncio
    async def test_a_session_idle_for_days_is_excluded_but_a_long_same_day_session_counts(
        self, resumed_session_repository: Awaitable[ModuleAnalyticsRepository]
    ):
        repo = await resumed_session_repository
        result = await repo.get_build_your_profile(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 4, 23, 59, tzinfo=timezone.utc),
            granularity="day",
        )

        # THEN all three count as completed, but only the same-day sessions enter the average
        assert result["summary"]["completed_users"] == 3
        assert result["summary"]["avg_completion_minutes"] == pytest.approx((20 + 10 * 60) / 2)


@pytest.fixture(scope="function")
async def funnel_repository(
    in_memory_application_database: Awaitable[AsyncIOMotorDatabase],
    in_memory_userdata_database: Awaitable[AsyncIOMotorDatabase],
    in_memory_metrics_database: Awaitable[AsyncIOMotorDatabase],
) -> ModuleAnalyticsRepository:
    """
    One user dropping off at each stage, so the funnel's counts can only be right if each stage is
    computed independently rather than everyone who finishes being counted at every earlier stage:
      - user-intro-only: INTRO, nothing else
      - user-experiences-only: INTRO, COLLECT_EXPERIENCES — drops off before skills
      - user-skills-only: INTRO, COLLECT_EXPERIENCES, DIVE_IN — drops off before completing
      - user-completed: INTRO, COLLECT_EXPERIENCES, DIVE_IN, ENDED
    """
    app_db = await in_memory_application_database
    metrics_db = await in_memory_metrics_database

    await app_db.get_collection(Collections.USER_PREFERENCES).insert_many([
        {"user_id": "user-intro-only"},
        {"user_id": "user-experiences-only"},
        {"user_id": "user-skills-only"},
        {"user_id": "user-completed"},
    ])

    ts = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    await metrics_db.get_collection(Collections.COMPASS_METRICS).insert_many([
        _phase_event("user-intro-only", 1, "INTRO", ts),
        _phase_event("user-experiences-only", 2, "INTRO", ts),
        _phase_event("user-experiences-only", 2, "COLLECT_EXPERIENCES", ts),
        _phase_event("user-skills-only", 3, "INTRO", ts),
        _phase_event("user-skills-only", 3, "COLLECT_EXPERIENCES", ts),
        _phase_event("user-skills-only", 3, "DIVE_IN", ts),
        _phase_event("user-completed", 4, "INTRO", ts),
        _phase_event("user-completed", 4, "COLLECT_EXPERIENCES", ts),
        _phase_event("user-completed", 4, "DIVE_IN", ts),
        _phase_event("user-completed", 4, "ENDED", ts),
    ])

    return ModuleAnalyticsRepository(app_db, await in_memory_userdata_database, metrics_db)


class TestBuildYourProfileFunnel:
    @pytest.mark.asyncio
    async def test_each_stage_counts_only_users_who_reached_at_least_that_far(
        self, funnel_repository: Awaitable[ModuleAnalyticsRepository]
    ):
        repo = await funnel_repository
        result = await repo.get_build_your_profile(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 1, 23, 59, tzinfo=timezone.utc),
            granularity="day",
        )

        assert result["phases"] == [
            {"id": "intro", "reached": 4},
            {"id": "experiences", "reached": 3},
            {"id": "skills", "reached": 2},
            {"id": "completed", "reached": 1},
        ]


def _sector_event(user_id: str, sector: str, is_priority: bool, inquiries: int, ts: datetime) -> dict:
    return {
        "event_type": EventType.SECTOR_ENGAGEMENT.value,
        "anonymized_user_id": _anon(user_id),
        "sector_name": sector,
        "is_priority": is_priority,
        "inquiry_count": inquiries,
        "timestamp": datetime_to_mongo_date(ts),
    }


def _conversation(user_id: str, created_at: datetime, *, as_string: bool = False) -> dict:
    return {
        "user_id": user_id,
        "created_at": created_at.astimezone(timezone.utc).isoformat() if as_string
        else datetime_to_mongo_date(created_at),
        "updated_at": datetime_to_mongo_date(created_at),
    }


_JAN_1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
_JAN_2 = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
_MAR_1 = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
_WINDOW_START = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
_WINDOW_END = datetime(2026, 1, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)


@pytest.fixture(scope="function")
async def career_explorer_repository(
    in_memory_application_database: Awaitable[AsyncIOMotorDatabase],
    in_memory_userdata_database: Awaitable[AsyncIOMotorDatabase],
    in_memory_metrics_database: Awaitable[AsyncIOMotorDatabase],
    in_memory_career_explorer_database: Awaitable[AsyncIOMotorDatabase],
) -> CareerExplorerModuleRepository:
    app_db = await in_memory_application_database
    userdata_db = await in_memory_userdata_database
    metrics_db = await in_memory_metrics_database
    ce_db = await in_memory_career_explorer_database

    await app_db.get_collection(Collections.USER_PREFERENCES).insert_many([
        {"user_id": "user-a"}, {"user_id": "user-b"}, {"user_id": "user-c"},
    ])
    await userdata_db.get_collection(Collections.PLAIN_PERSONAL_DATA).insert_many([
        {"user_id": "user-a", "data": {"institution_name": "Test School"}},
        {"user_id": "user-b", "data": {"institution_name": "Test School"}},
        {"user_id": "user-c", "data": {"institution_name": "Other School"}},
    ])
    await ce_db.get_collection(Collections.CAREER_EXPLORER_CONVERSATIONS).insert_many([
        _conversation("user-a", _JAN_1),
        _conversation("user-b", _JAN_2, as_string=True),
        _conversation("user-c", _MAR_1),
    ])
    await metrics_db.get_collection(Collections.COMPASS_METRICS).insert_many([
        _sector_event("user-a", "Healthcare", True, 3, _JAN_1),
        _sector_event("user-b", "Technology", False, 1, _JAN_2),
        _sector_event("user-c", "Healthcare", True, 2, _MAR_1),
    ])

    return CareerExplorerModuleRepository(app_db, userdata_db, metrics_db, ce_db)


class TestCareerExplorerCounts:
    @pytest.mark.asyncio
    async def test_should_count_everyone_who_started_in_the_window_however_their_date_was_stored(
        self, career_explorer_repository: Awaitable[CareerExplorerModuleRepository]
    ):
        # GIVEN two January conversations, one with a BSON-date created_at and one with an ISO string
        repo = await career_explorer_repository

        # WHEN the January window is aggregated across every institution
        actual = await repo.get_career_explorer(start_date=_WINDOW_START, end_date=_WINDOW_END)

        # THEN both are counted, and the March one is not
        assert actual["started"]["count"] == 2
        assert actual["total_registered_students"] == 3
        # AND the share is of everyone registered
        assert actual["started"]["percentage"] == round(2 / 3 * 100, 1)

    @pytest.mark.asyncio
    async def test_should_count_only_the_explorers_who_came_back(
        self, career_explorer_repository: Awaitable[CareerExplorerModuleRepository]
    ):
        # GIVEN user-a asked 3 times in January and user-b asked once
        repo = await career_explorer_repository

        # WHEN the January window is aggregated
        actual = await repo.get_career_explorer(start_date=_WINDOW_START, end_date=_WINDOW_END)

        # THEN only user-a counts as returning, as a share of those who started
        assert actual["returned_2_plus"]["count"] == 1
        assert actual["returned_2_plus"]["percentage"] == 50.0

    @pytest.mark.asyncio
    async def test_should_split_explorers_by_whether_their_sector_is_a_priority(
        self, career_explorer_repository: Awaitable[CareerExplorerModuleRepository]
    ):
        # GIVEN user-a in a priority sector and user-b outside one
        repo = await career_explorer_repository

        # WHEN the January window is aggregated
        actual = await repo.get_career_explorer(start_date=_WINDOW_START, end_date=_WINDOW_END)

        # THEN each lands on its own side of the split
        assert actual["priority_sector_users"] == 1
        assert actual["non_priority_sector_users"] == 1

    @pytest.mark.asyncio
    async def test_should_rank_sectors_by_the_inquiries_they_drew(
        self, career_explorer_repository: Awaitable[CareerExplorerModuleRepository]
    ):
        # GIVEN Healthcare drew 3 inquiries in January and Technology 1
        repo = await career_explorer_repository

        # WHEN the January window is aggregated
        actual = await repo.get_career_explorer(start_date=_WINDOW_START, end_date=_WINDOW_END)

        # THEN the busiest sector leads, carrying its priority flag and its distinct-user count
        assert [s["sector_name"] for s in actual["top_sectors"]] == ["Healthcare", "Technology"]
        assert actual["top_sectors"][0] == {
            "sector_name": "Healthcare",
            "is_priority": True,
            "total_inquiries": 3,
            "unique_users": 1,
        }


class TestCareerExplorerScoping:
    @pytest.mark.asyncio
    async def test_should_count_only_the_institutions_asked_for(
        self, career_explorer_repository: Awaitable[CareerExplorerModuleRepository]
    ):
        # GIVEN user-c belongs to Other School
        repo = await career_explorer_repository

        # WHEN only Test School is in scope, over a window wide enough to include March
        actual = await repo.get_career_explorer(
            start_date=_WINDOW_START,
            end_date=datetime(2026, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc),
            institution_names=["Test School"],
        )

        # THEN Other School's explorer is left out of every figure
        assert actual["total_registered_students"] == 2
        assert actual["started"]["count"] == 2
        assert actual["top_sectors"] == [
            {"sector_name": "Healthcare", "is_priority": True, "total_inquiries": 3, "unique_users": 1},
            {"sector_name": "Technology", "is_priority": False, "total_inquiries": 1, "unique_users": 1},
        ]

    @pytest.mark.asyncio
    async def test_should_return_zeroes_for_an_institution_nobody_belongs_to(
        self, career_explorer_repository: Awaitable[CareerExplorerModuleRepository]
    ):
        # GIVEN an institution with no registered students
        repo = await career_explorer_repository

        # WHEN it is the only one in scope
        actual = await repo.get_career_explorer(
            start_date=_WINDOW_START, end_date=_WINDOW_END, institution_names=["Nobody Here"]
        )

        # THEN the answer is a real, empty one rather than silently widening to everyone
        assert actual["total_registered_students"] == 0
        assert actual["started"] == {"count": 0, "percentage": 0.0}
        assert actual["returned_2_plus"] == {"count": 0, "percentage": 0.0}
        assert actual["top_sectors"] == []

    @pytest.mark.asyncio
    async def test_should_leave_out_activity_outside_the_window(
        self, career_explorer_repository: Awaitable[CareerExplorerModuleRepository]
    ):
        # GIVEN every recorded conversation and inquiry falls outside February
        repo = await career_explorer_repository

        # WHEN February alone is aggregated
        actual = await repo.get_career_explorer(
            start_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=timezone.utc),
        )

        # THEN nobody is reported as active, though the roster is still counted
        assert actual["total_registered_students"] == 3
        assert actual["started"]["count"] == 0
        assert actual["returned_2_plus"]["count"] == 0
        assert actual["top_sectors"] == []
