import asyncio

from app.app_config import get_application_config
from app.jobs.repository import IJobRepository, JobRepository
from app.jobs.service import IJobService, JobService
from app.matching.client import MatchingServiceClient

_job_repository_singleton: IJobRepository | None = None
_job_repository_lock = asyncio.Lock()

_job_service_singleton: IJobService | None = None
_job_service_lock = asyncio.Lock()


async def get_job_repository() -> IJobRepository:
    """Provide the singleton job repository, backed by the matching service HTTP API.

    Shared by ``JobService`` (``/jobs`` browse) and the job-demand analytics
    repository (Skills Analytics chart) so both read from the same source.
    """
    global _job_repository_singleton

    if _job_repository_singleton is None:
        async with _job_repository_lock:
            if _job_repository_singleton is None:
                config = get_application_config()
                client = MatchingServiceClient(
                    base_url=config.matching_service_url,
                    api_key=config.matching_service_api_key,
                )
                _job_repository_singleton = JobRepository(client)

    return _job_repository_singleton


async def get_job_service() -> IJobService:
    """Provide the singleton job service, backed by the matching service HTTP API.

    Jobs are no longer read from a Compass-owned MongoDB collection; the matching
    service is the source of truth (``GET /jobs`` and ``GET /jobs/stats``).
    """
    global _job_service_singleton

    if _job_service_singleton is None:
        async with _job_service_lock:
            if _job_service_singleton is None:
                _job_service_singleton = JobService(repository=await get_job_repository())

    return _job_service_singleton
