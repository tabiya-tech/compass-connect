import logging
from abc import ABC, abstractmethod
from typing import Literal, Optional

from pydantic import BaseModel

from app.analytics.types import PaginatedListMeta, PaginatedListResponse
from app.jobs.repository import IJobRepository, MatchingJobListItem


class JobStats(BaseModel):
    total: int
    sectors: int
    platforms: int


class JobDocument(BaseModel):
    model_config = {"extra": "ignore"}

    uuid: Optional[str] = None
    title: Optional[str] = None
    employer: Optional[str] = None
    category: Optional[str] = None
    employment_type: Optional[str] = None
    location: Optional[str] = None
    posted_date: Optional[str] = None
    closing_date: Optional[str] = None
    application_url: Optional[str] = None
    source_platform: Optional[str] = None
    skills: Optional[list[str]] = None


class MatchedJobDocument(BaseModel):
    """A job opportunity returned by the matching service for a specific user.

    Field names mirror the matching service response shape (opportunity_title, contract_type, URL).
    employer/location come directly from the matching service recommendation.
    """
    model_config = {"extra": "ignore"}

    uuid: Optional[str] = None
    opportunity_title: Optional[str] = None
    location: Optional[str] = None
    contract_type: Optional[str] = None
    URL: Optional[str] = None
    final_score: Optional[float] = None
    justification: Optional[str] = None
    rank: Optional[int] = None
    employer: Optional[str] = None
    category: Optional[str] = None
    posted_date: Optional[str] = None


SkillsSource = Literal["s&i", "programme", "none"]


class MatchedJobsResponse(BaseModel):
    """Envelope returned by GET /jobs/matched.

    `skills_source` tells the frontend which path produced the matches so it can pick
    the right empty-state copy / info banner without a second round-trip.
    """
    matches: list[MatchedJobDocument]
    skills_source: SkillsSource


class IJobService(ABC):
    """
    Interface for the Job Service.
    Allows to mock the service in tests.
    """

    @abstractmethod
    async def get_job_stats(self) -> JobStats:
        pass

    @abstractmethod
    async def list_jobs(
        self,
        search: Optional[str],
        category: Optional[str],
        employment_type: Optional[str],
        location: Optional[str],
        skills: Optional[str],
        days: Optional[int],
        cursor: Optional[str],
        limit: int,
        include: Optional[str],
    ) -> PaginatedListResponse["JobDocument"]:
        pass


class JobService(IJobService):
    """Business logic for jobs, backed by the matching service HTTP API.

    Compass no longer owns a jobs database; both browse (`/jobs`) and aggregate
    stats (`/jobs/stats`) are served by the matching service, and this service only
    maps the matching-service job shape onto the Compass `JobDocument` contract.
    """

    def __init__(self, repository: IJobRepository):
        self._repository = repository
        self._logger = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def _include_total(include: Optional[str]) -> bool:
        return include is not None and "count" in include.split(",")

    @staticmethod
    def _to_job_document(item: MatchingJobListItem) -> JobDocument:
        return JobDocument(
            uuid=item.uuid,
            title=item.opportunity_title,
            employer=item.employer,
            category=item.category,
            employment_type=item.employment_type or item.contract_type,
            location=item.location,
            posted_date=item.posted_date,
            closing_date=item.closing_date,
            application_url=item.url,
            source_platform=item.source_platform,
            skills=item.skills or None,
        )

    async def get_job_stats(self) -> JobStats:
        stats = await self._repository.fetch_stats()
        return JobStats(total=stats.total, sectors=stats.sectors, platforms=stats.platforms)

    async def list_jobs(
        self,
        search: Optional[str],
        category: Optional[str],
        employment_type: Optional[str],
        location: Optional[str],
        skills: Optional[str],
        days: Optional[int],
        cursor: Optional[str],
        limit: int,
        include: Optional[str],
    ) -> PaginatedListResponse[JobDocument]:
        page = await self._repository.fetch_jobs_page(
            cursor=cursor,
            limit=limit,
            search=search,
            category=category,
            employment_type=employment_type,
            location=location,
            skills=skills,
            days=days,
            include_total=self._include_total(include),
        )
        data = [self._to_job_document(item) for item in page.items]
        meta = PaginatedListMeta(
            limit=limit,
            next_cursor=page.next_cursor,
            has_more=page.next_cursor is not None,
            total=page.total,
        )
        return PaginatedListResponse(data=data, meta=meta)
