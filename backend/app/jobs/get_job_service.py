import asyncio

from app.app_config import get_application_config
from app.jobs.repository import JobRepository
from app.jobs.service import IJobService, JobService
from app.matching.client import MatchingServiceClient

_job_service_singleton: IJobService | None = None
_job_service_lock = asyncio.Lock()


async def get_job_service() -> IJobService:
    """Provide the singleton job service, backed by the matching service HTTP API.

    Jobs are no longer read from a Compass-owned MongoDB collection; the matching
    service is the source of truth (``GET /jobs`` and ``GET /jobs/stats``).
    """
    global _job_service_singleton

    if _job_service_singleton is None:
        async with _job_service_lock:
            if _job_service_singleton is None:
                config = get_application_config()
                client = MatchingServiceClient(
                    base_url=config.matching_service_url,
                    api_key=config.matching_service_api_key,
                )
                _job_service_singleton = JobService(repository=JobRepository(client))

    return _job_service_singleton
