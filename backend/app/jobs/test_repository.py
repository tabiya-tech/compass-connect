from unittest.mock import AsyncMock

import pytest

from app.jobs.repository import (
    JobRepository,
    MatchingJobsPage,
    MatchingJobsStats,
)


class TestJobRepository:
    @pytest.mark.asyncio
    async def test_fetch_jobs_page_calls_jobs_endpoint_with_filters(self):
        # GIVEN a matching-service client returning a page
        client = AsyncMock()
        client.get.return_value = MatchingJobsPage(items=[], next_cursor="next", total=7)
        repo = JobRepository(client=client)

        # WHEN fetching a filtered page with a total requested
        actual = await repo.fetch_jobs_page(
            cursor="cur", limit=10, search="nurse", category="Health",
            employment_type="full_time", location="Lusaka", skills="care",
            days=30, include_total=True,
        )

        # THEN the matching service /jobs endpoint is called with mapped query params
        assert actual.next_cursor == "next"
        assert actual.total == 7
        client.get.assert_awaited_once()
        called_args, called_kwargs = client.get.call_args
        assert called_args[0] is MatchingJobsPage
        assert called_args[1] == "/jobs"
        assert called_kwargs["params"] == {
            "cursor": "cur",
            "limit": 10,
            "search": "nurse",
            "category": "Health",
            "employment_type": "full_time",
            "location": "Lusaka",
            "skills": "care",
            "days": 30,
            "include_total": "true",
        }

    @pytest.mark.asyncio
    async def test_fetch_jobs_page_omits_include_total_when_false(self):
        # GIVEN a matching-service client
        client = AsyncMock()
        client.get.return_value = MatchingJobsPage(items=[])
        repo = JobRepository(client=client)

        # WHEN fetching a page without requesting the total
        await repo.fetch_jobs_page(include_total=False)

        # THEN include_total is sent as None so the service uses its default (false)
        assert client.get.call_args.kwargs["params"]["include_total"] is None

    @pytest.mark.asyncio
    async def test_fetch_stats_calls_stats_endpoint(self):
        # GIVEN a matching-service client returning stats
        client = AsyncMock()
        client.get.return_value = MatchingJobsStats(total=42, sectors=3, platforms=2)
        repo = JobRepository(client=client)

        # WHEN fetching stats
        actual = await repo.fetch_stats()

        # THEN the /jobs/stats endpoint is called and stats returned
        assert actual.total == 42
        assert actual.sectors == 3
        assert actual.platforms == 2
        called_args, _ = client.get.call_args
        assert called_args[0] is MatchingJobsStats
        assert called_args[1] == "/jobs/stats"
