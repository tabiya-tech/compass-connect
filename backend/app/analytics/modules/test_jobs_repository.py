"""
Tests for JobsModuleAnalyticsRepository — the per-jobseeker half of the Jobs module summary.

The figures are read back out of metric_events exactly as the metrics repository writes them:
one JOB_MATCHES_GENERATED document per matched profile, one JOB_VIEWED document per
(user, listing) pair.
"""
import hashlib
from typing import Awaitable

import pytest

from app.analytics.modules.repository import JobsModuleAnalyticsRepository
from app.metrics.constants import EventType
from app.server_dependencies.database_collections import Collections


def _anonymize(user_id: str) -> str:
    return hashlib.md5(user_id.encode(), usedforsecurity=False).hexdigest()


def _matches_generated_doc(user_id: str, *, matches_count: int = 3) -> dict:
    return {
        "event_type": EventType.JOB_MATCHES_GENERATED.value,
        "event_type_name": EventType.JOB_MATCHES_GENERATED.name,
        "anonymized_user_id": _anonymize(user_id),
        "matches_count": matches_count,
        "match_generation_count": 1,
    }


def _job_viewed_doc(user_id: str, job_id: str) -> dict:
    return {
        "event_type": EventType.JOB_VIEWED.value,
        "event_type_name": EventType.JOB_VIEWED.name,
        "anonymized_user_id": _anonymize(user_id),
        "job_id": job_id,
        "view_count": 1,
    }


@pytest.fixture(scope="function")
async def repository_with_dbs(
    in_memory_application_database, in_memory_userdata_database, in_memory_metrics_database
):
    application_db = await in_memory_application_database
    userdata_db = await in_memory_userdata_database
    metrics_db = await in_memory_metrics_database
    repository = JobsModuleAnalyticsRepository(application_db, userdata_db, metrics_db)
    return repository, application_db, userdata_db, metrics_db


async def _given_registered_users(application_db, user_ids: list[str]) -> None:
    await application_db.get_collection(Collections.USER_PREFERENCES).insert_many(
        [{"user_id": user_id} for user_id in user_ids]
    )


async def _given_users_at_institution(userdata_db, institution_name: str, user_ids: list[str]) -> None:
    await userdata_db.get_collection(Collections.PLAIN_PERSONAL_DATA).insert_many(
        [{"user_id": user_id, "data": {"institution_name": institution_name}} for user_id in user_ids]
    )


class TestGetJobsEngagement:
    @pytest.mark.asyncio
    async def test_returns_zeros_when_nothing_has_happened(self, repository_with_dbs):
        # GIVEN registered users but no matching runs and no job views
        repository, application_db, _, _ = await repository_with_dbs
        await _given_registered_users(application_db, ["user-1", "user-2"])

        # WHEN the engagement figures are read
        actual = await repository.get_jobs_engagement()

        # THEN every figure is zero rather than absent
        assert actual == {
            "profiles_with_matches": 0,
            "profiles_with_matches_percentage": 0.0,
            "jobs_viewed_per_user": 0.0,
        }

    @pytest.mark.asyncio
    async def test_counts_matched_profiles_as_a_share_of_registered_users(self, repository_with_dbs):
        # GIVEN four registered users, of whom one has been matched to jobs
        repository, application_db, _, metrics_db = await repository_with_dbs
        await _given_registered_users(application_db, ["user-1", "user-2", "user-3", "user-4"])
        await metrics_db.get_collection(Collections.COMPASS_METRICS).insert_one(
            _matches_generated_doc("user-1")
        )

        # WHEN the engagement figures are read
        actual = await repository.get_jobs_engagement()

        # THEN one profile has matches, which is a quarter of everyone registered
        assert actual["profiles_with_matches"] == 1
        assert actual["profiles_with_matches_percentage"] == 25.0

    @pytest.mark.asyncio
    async def test_averages_jobs_viewed_over_the_jobseekers_who_viewed_any(self, repository_with_dbs):
        # GIVEN ten registered users, of whom one viewed three listings and one viewed two
        repository, application_db, _, metrics_db = await repository_with_dbs
        await _given_registered_users(application_db, [f"user-{index}" for index in range(10)])
        await metrics_db.get_collection(Collections.COMPASS_METRICS).insert_many(
            [
                _job_viewed_doc("user-0", "job-a"),
                _job_viewed_doc("user-0", "job-b"),
                _job_viewed_doc("user-0", "job-c"),
                _job_viewed_doc("user-1", "job-a"),
                _job_viewed_doc("user-1", "job-d"),
            ]
        )

        # WHEN the engagement figures are read
        actual = await repository.get_jobs_engagement()

        # THEN the average is over the two viewers, not over all ten registered users
        assert actual["jobs_viewed_per_user"] == 2.5

    @pytest.mark.asyncio
    async def test_scopes_every_figure_to_the_requested_institution(self, repository_with_dbs):
        # GIVEN two institutions, each with users who have been matched and have viewed listings
        repository, application_db, userdata_db, metrics_db = await repository_with_dbs
        await _given_registered_users(application_db, ["in-1", "in-2", "out-1", "out-2"])
        await _given_users_at_institution(userdata_db, "Lusaka College", ["in-1", "in-2"])
        await _given_users_at_institution(userdata_db, "Ndola Institute", ["out-1", "out-2"])
        await metrics_db.get_collection(Collections.COMPASS_METRICS).insert_many(
            [
                _matches_generated_doc("in-1"),
                _matches_generated_doc("out-1"),
                _matches_generated_doc("out-2"),
                _job_viewed_doc("in-1", "job-a"),
                _job_viewed_doc("out-1", "job-a"),
                _job_viewed_doc("out-1", "job-b"),
                _job_viewed_doc("out-2", "job-c"),
            ]
        )

        # WHEN the engagement figures are read for one institution
        actual = await repository.get_jobs_engagement(["Lusaka College"])

        # THEN only that institution's jobseekers count, in the figures and in the denominator
        assert actual == {
            "profiles_with_matches": 1,
            "profiles_with_matches_percentage": 50.0,
            "jobs_viewed_per_user": 1.0,
        }

    @pytest.mark.asyncio
    async def test_an_institution_with_no_users_is_an_empty_answer_not_everyone(self, repository_with_dbs):
        # GIVEN matched and viewing users, none of whom belong to the requested institution
        repository, application_db, userdata_db, metrics_db = await repository_with_dbs
        await _given_registered_users(application_db, ["user-1"])
        await _given_users_at_institution(userdata_db, "Lusaka College", ["user-1"])
        await metrics_db.get_collection(Collections.COMPASS_METRICS).insert_many(
            [_matches_generated_doc("user-1"), _job_viewed_doc("user-1", "job-a")]
        )

        # WHEN the engagement figures are read for an institution with nobody in it
        actual = await repository.get_jobs_engagement(["Empty Academy"])

        # THEN the answer is zeros, not the unscoped totals
        assert actual == {
            "profiles_with_matches": 0,
            "profiles_with_matches_percentage": 0.0,
            "jobs_viewed_per_user": 0.0,
        }
