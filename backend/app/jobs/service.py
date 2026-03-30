import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Any, Dict, Optional

from fastapi import HTTPException
from app.analytics.types import PaginatedListMeta, PaginatedListResponse
from app.jobs.repository import IJobRepository
from pydantic import BaseModel


class JobStats(BaseModel):
    total: int
    sectors: int
    platforms: int


class JobDocument(BaseModel):
    model_config = {"extra": "ignore"}

    uuid: Optional[str] = None
    opportunity_title: Optional[str] = None
    employer: Optional[str] = None
    category: Optional[str] = None
    contract_type: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    posted_date: Optional[str] = None
    closing_date: Optional[str] = None
    URL: Optional[str] = None
    source_platform: Optional[str] = None
    attributes: Optional[dict] = None


class MatchedJobDocument(BaseModel):
    """Job document returned by the matching service, optionally enriched from the jobs collection."""
    model_config = {"extra": "ignore"}

    uuid: Optional[str] = None
    opportunity_title: Optional[str] = None
    location: Optional[str] = None
    contract_type: Optional[str] = None
    URL: Optional[str] = None
    final_score: Optional[float] = None
    justification: Optional[str] = None
    rank: Optional[int] = None
    # Enriched from the jobs collection
    employer: Optional[str] = None
    category: Optional[str] = None
    posted_date: Optional[str] = None


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
        category: Optional[str],
        employment_type: Optional[str],
        location: Optional[str],
        days: Optional[int],
        cursor: Optional[str],
        limit: int,
        include: Optional[str],
    ) -> PaginatedListResponse[JobDocument]:
        pass

    @abstractmethod
    async def get_jobs_by_uuids(self, uuids: list[str]) -> dict[str, JobDocument]:
        pass


class JobService(IJobService):
    """
    JobService class is responsible for business logic related to jobs.
    """

    def __init__(self, repository: IJobRepository):
        self._repository = repository
        self._logger = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def _build_jobs_mongo_filter(
        category: Optional[str],
        employment_type: Optional[str],
        location: Optional[str],
        days: Optional[int],
    ) -> Dict[str, Any]:
        fquery: Dict[str, Any] = {}
        if category:
            fquery["category"] = category
        if employment_type:
            fquery["contract_type"] = employment_type
        if location:
            fquery["location"] = location
        if days is not None:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
            fquery["posted_date"] = {"$gte": cutoff_date}
        return fquery

    @staticmethod
    def _parse_cursor_offset(cursor: Optional[str]) -> int:
        if cursor is None:
            return 0
        try:
            return int(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid cursor") from exc

    @staticmethod
    def _include_total(include: Optional[str]) -> bool:
        return include is not None and "count" in include.split(",")

    async def get_job_stats(self) -> JobStats:
        total, sectors, platforms = await asyncio.gather(
            self._repository.count_jobs({}),
            self._repository.distinct_values("category", {}),
            self._repository.distinct_values("source_platform", {}),
        )
        return JobStats(total=total, sectors=len(sectors), platforms=len(platforms))

    async def list_jobs(
        self,
        category: Optional[str],
        employment_type: Optional[str],
        location: Optional[str],
        days: Optional[int],
        cursor: Optional[str],
        limit: int,
        include: Optional[str],
    ) -> PaginatedListResponse[JobDocument]:
        filter_query = self._build_jobs_mongo_filter(category, employment_type, location, days)
        include_count = self._include_total(include)
        offset = self._parse_cursor_offset(cursor)

        docs = await self._repository.list_jobs(filter_query=filter_query, offset=offset, limit=limit)

        has_more = len(docs) > limit
        page_docs = docs[:limit]
        next_cursor = str(offset + limit) if has_more else None

        job_documents = [JobDocument.model_validate(doc) for doc in page_docs]

        total = await self._repository.count_jobs(filter_query) if include_count else None
        meta = PaginatedListMeta(
            limit=limit,
            next_cursor=next_cursor,
            has_more=has_more,
            total=total if include_count else None,
        )
        return PaginatedListResponse(data=job_documents, meta=meta)

    async def get_jobs_by_uuids(self, uuids: list[str]) -> dict[str, JobDocument]:
        docs = await self._repository.find_by_uuids(uuids)
        return {doc["uuid"]: JobDocument.model_validate(doc) for doc in docs if "uuid" in doc}
