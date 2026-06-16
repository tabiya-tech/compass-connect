import logging
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field

from app.matching.client import MatchingServiceClient


class MatchingJobListItem(BaseModel):
    """One job from the matching service ``GET /jobs`` (subset of fields we consume).

    The matching service is the single source of truth for jobs; Compass no longer reads
    a jobs MongoDB collection. ``extra="ignore"`` keeps us forward-compatible with the
    matching service adding fields we don't (yet) surface.
    """

    model_config = {"extra": "ignore"}

    uuid: Optional[str] = None
    url: Optional[str] = None
    opportunity_title: Optional[str] = None
    location: Optional[str] = None
    employer: Optional[str] = None
    employment_type: Optional[str] = None
    contract_type: Optional[str] = None
    closing_date: Optional[str] = None
    posted_date: Optional[str] = None
    category: Optional[str] = None
    source_platform: Optional[str] = None
    skills: list[str] = Field(default_factory=list)


class MatchingJobsPage(BaseModel):
    """Cursor-paginated page returned by the matching service ``GET /jobs``."""

    model_config = {"extra": "ignore"}

    items: list[MatchingJobListItem] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    total: Optional[int] = None


class MatchingJobsStats(BaseModel):
    """Aggregate counts returned by the matching service ``GET /jobs/stats``."""

    model_config = {"extra": "ignore"}

    total: int = 0
    sectors: int = 0
    platforms: int = 0


class IJobRepository(ABC):
    """
    Interface for the Job Repository.
    Allows to mock the repository in tests.
    """

    @abstractmethod
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
        pass

    @abstractmethod
    async def fetch_stats(self) -> MatchingJobsStats:
        pass


class JobRepository(IJobRepository):
    """Reads jobs from the matching service HTTP API (``/jobs`` and ``/jobs/stats``)."""

    def __init__(self, client: MatchingServiceClient):
        self._client = client
        self._logger = logging.getLogger(self.__class__.__name__)

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
        params = {
            "cursor": cursor,
            "limit": limit,
            "search": search,
            "category": category,
            "employment_type": employment_type,
            "location": location,
            "skills": skills,
            "days": days,
            # Send only when set; the matching service defaults include_total to false.
            "include_total": "true" if include_total else None,
        }
        return await self._client.get(MatchingJobsPage, "/jobs", params=params)

    async def fetch_stats(self) -> MatchingJobsStats:
        return await self._client.get(MatchingJobsStats, "/jobs/stats")
