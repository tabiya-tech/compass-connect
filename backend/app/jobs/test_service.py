from typing import Optional

import pytest

from app.jobs.repository import (
    IJobRepository,
    MatchingJobListItem,
    MatchingJobsPage,
    MatchingJobsStats,
)
from app.jobs.service import JobService


class _FakeJobRepository(IJobRepository):
    def __init__(self, page: MatchingJobsPage, stats: MatchingJobsStats):
        self._page = page
        self._stats = stats
        self.last_kwargs: Optional[dict] = None

    async def fetch_jobs_page(self, **kwargs) -> MatchingJobsPage:
        self.last_kwargs = kwargs
        return self._page

    async def fetch_stats(self) -> MatchingJobsStats:
        return self._stats


def _page(items, next_cursor=None, total=None) -> MatchingJobsPage:
    return MatchingJobsPage(items=items, next_cursor=next_cursor, total=total)


class TestJobServiceListJobs:
    @pytest.mark.asyncio
    async def test_maps_matching_item_to_job_document(self):
        # GIVEN a matching-service page with one fully-populated item
        given_item = MatchingJobListItem(
            uuid="job-1",
            url="https://example.com/apply",
            opportunity_title="Software Engineer",
            location="Lusaka",
            employer="TechCorp",
            employment_type="full_time",
            contract_type="permanent",
            closing_date="2026-07-01",
            posted_date="2026-06-01",
            category="Engineering",
            source_platform="BrighterMonday",
            skills=["Python", "SQL"],
        )
        repo = _FakeJobRepository(_page([given_item]), MatchingJobsStats())
        service = JobService(repository=repo)

        # WHEN listing jobs
        actual = await service.list_jobs(
            search=None, category=None, employment_type=None, location=None,
            skills=None, days=None, cursor=None, limit=20, include=None,
        )

        # THEN the matching item is mapped onto the Compass JobDocument contract
        assert len(actual.data) == 1
        doc = actual.data[0]
        assert doc.uuid == "job-1"
        assert doc.title == "Software Engineer"
        assert doc.application_url == "https://example.com/apply"
        assert doc.employer == "TechCorp"
        assert doc.employment_type == "full_time"
        assert doc.category == "Engineering"
        assert doc.source_platform == "BrighterMonday"
        assert doc.posted_date == "2026-06-01"
        assert doc.closing_date == "2026-07-01"
        assert doc.skills == ["Python", "SQL"]

    @pytest.mark.asyncio
    async def test_employment_type_falls_back_to_contract_type(self):
        # GIVEN an item with no employment_type but a contract_type
        given_item = MatchingJobListItem(opportunity_title="X", contract_type="full_time")
        repo = _FakeJobRepository(_page([given_item]), MatchingJobsStats())
        service = JobService(repository=repo)

        # WHEN listing jobs
        actual = await service.list_jobs(
            search=None, category=None, employment_type=None, location=None,
            skills=None, days=None, cursor=None, limit=20, include=None,
        )

        # THEN employment_type is taken from contract_type
        assert actual.data[0].employment_type == "full_time"

    @pytest.mark.asyncio
    async def test_pagination_meta_reflects_next_cursor(self):
        # GIVEN a page that has a next cursor and a total
        repo = _FakeJobRepository(
            _page([MatchingJobListItem(opportunity_title="A")], next_cursor="abc", total=99),
            MatchingJobsStats(),
        )
        service = JobService(repository=repo)

        # WHEN listing jobs with include=count
        actual = await service.list_jobs(
            search=None, category=None, employment_type=None, location=None,
            skills=None, days=None, cursor=None, limit=5, include="count",
        )

        # THEN the meta carries the cursor, has_more, limit and total through
        assert actual.meta.limit == 5
        assert actual.meta.next_cursor == "abc"
        assert actual.meta.has_more is True
        assert actual.meta.total == 99

    @pytest.mark.asyncio
    async def test_last_page_has_no_next_cursor(self):
        # GIVEN a page with no next cursor
        repo = _FakeJobRepository(_page([], next_cursor=None), MatchingJobsStats())
        service = JobService(repository=repo)

        # WHEN listing jobs
        actual = await service.list_jobs(
            search=None, category=None, employment_type=None, location=None,
            skills=None, days=None, cursor=None, limit=20, include=None,
        )

        # THEN has_more is False and next_cursor is None
        assert actual.meta.has_more is False
        assert actual.meta.next_cursor is None
        assert actual.meta.total is None

    @pytest.mark.asyncio
    async def test_filters_and_cursor_forwarded_to_repository(self):
        # GIVEN a service over a fake repository
        repo = _FakeJobRepository(_page([]), MatchingJobsStats())
        service = JobService(repository=repo)

        # WHEN listing jobs with filters, a cursor and include=count
        await service.list_jobs(
            search="nurse", category="Health", employment_type="full_time",
            location="Lusaka", skills="care", days=30, cursor="cur", limit=10, include="count",
        )

        # THEN every filter, the cursor, the limit and include_total reach the repository
        assert repo.last_kwargs == {
            "cursor": "cur",
            "limit": 10,
            "search": "nurse",
            "category": "Health",
            "employment_type": "full_time",
            "location": "Lusaka",
            "skills": "care",
            "days": 30,
            "include_total": True,
        }

    @pytest.mark.asyncio
    async def test_include_total_false_when_not_requested(self):
        # GIVEN a service over a fake repository
        repo = _FakeJobRepository(_page([]), MatchingJobsStats())
        service = JobService(repository=repo)

        # WHEN listing jobs without include=count
        await service.list_jobs(
            search=None, category=None, employment_type=None, location=None,
            skills=None, days=None, cursor=None, limit=20, include=None,
        )

        # THEN include_total is not requested from the data source
        assert repo.last_kwargs["include_total"] is False


class TestJobServiceStats:
    @pytest.mark.asyncio
    async def test_get_job_stats_passes_through_matching_service_counts(self):
        # GIVEN the matching service reports aggregate counts
        repo = _FakeJobRepository(_page([]), MatchingJobsStats(total=42, sectors=3, platforms=2))
        service = JobService(repository=repo)

        # WHEN fetching job stats
        actual = await service.get_job_stats()

        # THEN the counts are surfaced unchanged
        assert actual.total == 42
        assert actual.sectors == 3
        assert actual.platforms == 2
