"""
Tests for the job-demand analytics repository.

The repo aggregates over the matching-service ``/jobs`` HTTP API (via
``IJobRepository``); these tests fake that interface to exercise the
pagination, filtering, and aggregation logic in isolation.
"""
from typing import Optional

import pytest

from app.analytics.job_demand import sector_mapping
from app.analytics.job_demand.repository import JobDemandAnalyticsRepository
from app.analytics.job_demand.types import JobDemandStatsResponse
from app.jobs.repository import IJobRepository, MatchingJobListItem, MatchingJobsPage, MatchingJobsStats


class _FakeJobRepository(IJobRepository):
    """In-memory ``IJobRepository`` honoring the matching service's ``location``
    query param (case-insensitive substring) and cursor pagination. Other filter
    params are not exercised by the analytics repo and are accepted but ignored."""

    def __init__(self, jobs: list[MatchingJobListItem], page_size: int = 100):
        self._jobs = jobs
        self._page_size = page_size
        self.calls: list[dict] = []

    async def fetch_jobs_page(
        self,
        *,
        cursor: Optional[str] = None,
        limit: int = 20,
        search: Optional[str] = None,
        category: Optional[str] = None,
        employment_type: Optional[str] = None,
        location: Optional[str] = None,
        skills: Optional[str] = None,
        days: Optional[int] = None,
        include_total: bool = False,
    ) -> MatchingJobsPage:
        self.calls.append({"cursor": cursor, "limit": limit, "location": location})

        filtered = self._jobs
        if location:
            needle = location.strip().lower()
            filtered = [j for j in filtered if j.location and needle in j.location.lower()]

        start = int(cursor) if cursor else 0
        page_size = min(limit, self._page_size)
        end = start + page_size
        items = filtered[start:end]
        next_cursor = str(end) if end < len(filtered) else None
        return MatchingJobsPage(items=items, next_cursor=next_cursor, total=None)

    async def fetch_stats(self) -> MatchingJobsStats:
        return MatchingJobsStats(total=len(self._jobs), sectors=0, platforms=0)


def _job(uuid: str, *, location: str = "Lusaka",
         category: Optional[str] = None,
         skills: Optional[list[str]] = None) -> MatchingJobListItem:
    return MatchingJobListItem(
        uuid=uuid,
        location=location,
        category=category,
        skills=skills or [],
    )


# ---------------------------------------------------------------------------
# Core aggregation
# ---------------------------------------------------------------------------

class TestGetJobDemandStats:
    @pytest.fixture()
    def populated_repository(self) -> JobDemandAnalyticsRepository:
        """
        Seeds a job set covering every branch:

          j1 (Lusaka, Lusaka, Zambia) : Python, SQL
          j2 (Lusaka)                 : Python (x2 -> dedupe), Excel
          j3 (Copperbelt)             : Python
          j4 (Lusaka)                 : no skills
          j5 (Lusaka)                 : empty-string skill only -> still 'no skills'
          j6 (Lusaka)                 : SQL
          j7 (Lusaka)                 : Welding
          j8 (Lusaka)                 : Welding
        """
        jobs = [
            _job("j1", location="Lusaka, Lusaka, Zambia", skills=["Python", "SQL"]),
            _job("j2", location="Lusaka", skills=["Python", "Python", "Excel"]),
            _job("j3", location="Copperbelt", skills=["Python"]),
            _job("j4", location="Lusaka"),
            _job("j5", location="Lusaka", skills=[""]),
            _job("j6", location="Lusaka", skills=["SQL"]),
            _job("j7", location="Lusaka", skills=["Welding"]),
            _job("j8", location="Lusaka", skills=["Welding"]),
        ]
        return JobDemandAnalyticsRepository(_FakeJobRepository(jobs))

    @pytest.mark.asyncio
    async def test_total_jobs_counts_every_posting(self, populated_repository):
        result: JobDemandStatsResponse = await populated_repository.get_job_demand_stats(limit=10)
        # Every posting in the scan window — including j4/j5 with no usable skills.
        assert result.total_jobs == 8

    @pytest.mark.asyncio
    async def test_jobs_with_linked_skills_excludes_empty(self, populated_repository):
        result = await populated_repository.get_job_demand_stats(limit=10)
        # j4 (no skills), j5 (only empty-string) excluded; six others remain.
        assert result.jobs_with_linked_skills == 6

    @pytest.mark.asyncio
    async def test_ranking_order_and_dedupe_per_job(self, populated_repository):
        result = await populated_repository.get_job_demand_stats(limit=10)
        ranking = [(e.skill_label, e.jobs_count) for e in result.top_skills_in_demand]
        # Python: j1,j2,j3 = 3 (j2 lists it twice -> still 1 for that job).
        # SQL & Welding tie at 2 — label asc breaks the tie.
        assert ranking == [("Python", 3), ("SQL", 2), ("Welding", 2), ("Excel", 1)]

    @pytest.mark.asyncio
    async def test_location_filter_passed_to_matching_service(self, populated_repository):
        # WHEN filtering by Lusaka
        result = await populated_repository.get_job_demand_stats(limit=10, location="Lusaka")
        # THEN the matching service receives the location param and j3 (Copperbelt) drops out.
        fake: _FakeJobRepository = populated_repository._job_repository  # type: ignore[assignment]
        assert all(call["location"] == "Lusaka" for call in fake.calls)
        assert result.total_jobs == 7
        assert result.jobs_with_linked_skills == 5

    @pytest.mark.asyncio
    async def test_limit_is_respected(self, populated_repository):
        result = await populated_repository.get_job_demand_stats(limit=2)
        assert [e.skill_label for e in result.top_skills_in_demand] == ["Python", "SQL"]

    @pytest.mark.asyncio
    async def test_empty_collection_returns_zeroes(self):
        repo = JobDemandAnalyticsRepository(_FakeJobRepository([]))
        result = await repo.get_job_demand_stats(limit=10)
        assert result.total_jobs == 0
        assert result.jobs_with_linked_skills == 0
        assert result.top_skills_in_demand == []

    @pytest.mark.asyncio
    async def test_paginates_across_multiple_pages(self):
        # Many pages worth of jobs given the repo's page size; ensure the loop
        # follows the cursor and aggregates across pages.
        from app.analytics.job_demand.repository import _PAGE_SIZE
        total_jobs_to_seed = _PAGE_SIZE * 12 + 10  # 12 full pages + a partial
        jobs = [_job(f"j{i}", skills=["Python"]) for i in range(total_jobs_to_seed)]
        fake = _FakeJobRepository(jobs, page_size=_PAGE_SIZE)
        repo = JobDemandAnalyticsRepository(fake)
        result = await repo.get_job_demand_stats(limit=10)
        # Expect ceil(total / page_size) page fetches.
        expected_calls = (total_jobs_to_seed + _PAGE_SIZE - 1) // _PAGE_SIZE
        assert len(fake.calls) == expected_calls
        assert result.total_jobs == total_jobs_to_seed
        assert result.jobs_with_linked_skills == total_jobs_to_seed
        assert [(e.skill_label, e.jobs_count) for e in result.top_skills_in_demand] == [
            ("Python", total_jobs_to_seed)
        ]


# ---------------------------------------------------------------------------
# Sector filter
# ---------------------------------------------------------------------------

class TestSectorFilter:
    @pytest.fixture(autouse=True)
    def _fixed_sector_map(self, monkeypatch):
        # Pin a known sector map so these tests don't depend on the regenerable
        # sector_category_map.json artifact.
        monkeypatch.setattr(sector_mapping, "_cache", {
            "IT & Telecoms": "ICT",
            "Banking & Financial Services": "Finance & Insurance",
            "Tenders & RFPs": None,
        })

    @pytest.fixture()
    def sectored_repository(self) -> JobDemandAnalyticsRepository:
        """
        Jobs spanning categories that map to different institution sectors:

          a (Lusaka,     "IT & Telecoms, Software")        : Python   -> ICT
          b (Lusaka,     "IT & Telecoms")                  : Docker   -> ICT
          c (Copperbelt, "IT & Telecoms")                  : Python   -> ICT (other province)
          d (Lusaka,     "Banking & Financial Services")   : Excel    -> Finance & Insurance
          e (Lusaka,     "Tenders & RFPs, IT & Telecoms")  : Python   -> leading token maps to null
          f (Lusaka,     no category)                      : Python   -> no sector at all
        """
        jobs = [
            _job("a", location="Lusaka", category="IT & Telecoms, Software", skills=["Python"]),
            _job("b", location="Lusaka", category="IT & Telecoms", skills=["Docker"]),
            _job("c", location="Copperbelt", category="IT & Telecoms", skills=["Python"]),
            _job("d", location="Lusaka", category="Banking & Financial Services", skills=["Excel"]),
            _job("e", location="Lusaka", category="Tenders & RFPs, IT & Telecoms", skills=["Python"]),
            _job("f", location="Lusaka", category=None, skills=["Python"]),
        ]
        return JobDemandAnalyticsRepository(_FakeJobRepository(jobs))

    @pytest.mark.asyncio
    async def test_sector_filters_to_mapped_category_prefix(self, sectored_repository):
        # WHEN filtering by the ICT sector
        result = await sectored_repository.get_job_demand_stats(limit=10, sector="ICT")
        # THEN only a, b, c (leading token "IT & Telecoms") count; d/e/f drop.
        assert result.total_jobs == 3
        assert result.jobs_with_linked_skills == 3
        ranking = {e.skill_label: e.jobs_count for e in result.top_skills_in_demand}
        assert ranking == {"Python": 2, "Docker": 1}

    @pytest.mark.asyncio
    async def test_sector_and_province_combine(self, sectored_repository):
        # WHEN filtering by ICT sector AND the Lusaka province
        result = await sectored_repository.get_job_demand_stats(
            limit=10, location="Lusaka", sector="ICT"
        )
        # THEN c (Copperbelt) also drops -> only a, b remain
        assert result.total_jobs == 2
        ranking = {e.skill_label: e.jobs_count for e in result.top_skills_in_demand}
        assert ranking == {"Python": 1, "Docker": 1}

    @pytest.mark.asyncio
    async def test_no_supply_sector_returns_empty(self, sectored_repository):
        # WHEN filtering by a sector with no aligned job-category supply
        result = await sectored_repository.get_job_demand_stats(limit=10, sector="Households")
        # THEN the chart is empty (not silently market-wide)
        assert result.total_jobs == 0
        assert result.jobs_with_linked_skills == 0
        assert result.top_skills_in_demand == []
