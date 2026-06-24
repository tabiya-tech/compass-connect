"""
Job-demand analytics: rank skills across job postings.

Reads from the matching service's ``/jobs`` HTTP API via ``IJobRepository`` —
the same source the Job Postings tab and matched-jobs endpoint already use,
so the Skills Analytics chart stays consistent with what users browse.
"""
import logging
from abc import ABC, abstractmethod
from collections import Counter
from typing import Optional

from app.analytics.job_demand.sector_mapping import (
    _NO_FILTER_SENTINELS,
    _category_to_sector,
    category_leading_token,
)
from app.analytics.job_demand.types import JobDemandEntry, JobDemandStatsResponse
from app.jobs.repository import IJobRepository, MatchingJobListItem

logger = logging.getLogger(__name__)

# Per-page size we request from the matching service.
_PAGE_SIZE = 20

# Hard ceiling on jobs scanned per request — defensive against an unbounded
# matching-service backlog. Far above the current ~1.4k postings; revisit if
# the chart starts truncating data in prod.
_MAX_JOBS_SCANNED = 10_000


class IJobDemandAnalyticsRepository(ABC):
    """Interface for job-demand analytics aggregation queries."""

    @abstractmethod
    async def get_job_demand_stats(
        self, limit: int, location: Optional[str] = None, sector: Optional[str] = None
    ) -> JobDemandStatsResponse:
        """Return the top in-demand skills across job postings, optionally filtered by province/sector."""
        raise NotImplementedError()


def _sector_prefixes(sector: Optional[str]) -> Optional[set[str]]:
    """Resolve an institution sector to the set of ``category`` leading-token
    prefixes that map to it. Returns ``None`` when no sector filter applies and
    an empty set when the sector has no aligned categories (no-supply: the chart
    must be empty rather than fall back to market-wide data)."""
    if sector is None:
        return None
    key = sector.strip().lower()
    if key in _NO_FILTER_SENTINELS:
        return None
    return {
        cat for cat, sec in _category_to_sector().items()
        if isinstance(sec, str) and sec.strip().lower() == key
    }


def _job_matches_sector(job: MatchingJobListItem, prefixes: set[str]) -> bool:
    """Whether ``job.category``'s leading token maps to the requested sector."""
    token = category_leading_token(job.category)
    return token is not None and token in prefixes


class JobDemandAnalyticsRepository(IJobDemandAnalyticsRepository):
    """Aggregates skill demand by scanning the matching service ``/jobs`` API."""

    def __init__(self, job_repository: IJobRepository):
        self._job_repository = job_repository

    async def get_job_demand_stats(
        self, limit: int, location: Optional[str] = None, sector: Optional[str] = None
    ) -> JobDemandStatsResponse:
        """
        Rank skills across job postings.

        :param limit: max skills to return.
        :param location: optional province filter — passed to the matching
            service as the ``location`` query param.
        :param sector: optional institution-sector filter; resolved via the
            generated ``sector_category_map`` and applied client-side against
            ``job.category``'s leading token (the matching service ``category``
            query param only accepts one value, but a sector can map to many).
        """
        sector_prefixes = _sector_prefixes(sector)
        # No-supply sector → empty chart (deliberately not market-wide).
        if sector_prefixes is not None and not sector_prefixes:
            return JobDemandStatsResponse(
                total_jobs=0, jobs_with_linked_skills=0, top_skills_in_demand=[]
            )

        total_jobs = 0
        jobs_with_skills = 0
        skill_counts: Counter[str] = Counter()
        cursor: Optional[str] = None
        scanned = 0

        while True:
            page = await self._job_repository.fetch_jobs_page(
                cursor=cursor,
                limit=_PAGE_SIZE,
                location=location,
            )
            for job in page.items:
                if sector_prefixes is not None and not _job_matches_sector(job, sector_prefixes):
                    continue
                total_jobs += 1
                # Dedupe within a posting so a job listing the same skill twice
                # counts once. Drop empty strings defensively.
                unique_skills = {s for s in (job.skills or []) if isinstance(s, str) and s}
                if unique_skills:
                    jobs_with_skills += 1
                    skill_counts.update(unique_skills)

            scanned += len(page.items)
            if not page.next_cursor or not page.items:
                break
            if scanned >= _MAX_JOBS_SCANNED:
                logger.warning(
                    "Job-demand scan hit the %s-job ceiling; results truncated",
                    _MAX_JOBS_SCANNED,
                )
                break
            cursor = page.next_cursor

        # Stable sort: highest count first, then label asc as tiebreak.
        ranked = sorted(skill_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        top_skills_in_demand = [
            JobDemandEntry(skill_label=label, jobs_count=count) for label, count in ranked
        ]

        return JobDemandStatsResponse(
            total_jobs=total_jobs,
            jobs_with_linked_skills=jobs_with_skills,
            top_skills_in_demand=top_skills_in_demand,
        )
