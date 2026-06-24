"""
Job-demand analytics routes.

Backs the "Top Skills In Demand (Job Postings)" chart in the admin Skills
Analytics tab.
"""
import logging
from http import HTTPStatus
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.analytics.job_demand.repository import (
    IJobDemandAnalyticsRepository,
    JobDemandAnalyticsRepository,
)
from app.analytics.job_demand.sector_mapping import validate_sector_map
from app.analytics.job_demand.types import JobDemandStatsResponse
from app.constants.errors import HTTPErrorResponse
from app.jobs.get_job_service import get_job_repository
from app.jobs.repository import IJobRepository
from app.users.auth import Authentication
from app.users.access_role import AccessRole, get_access_role_dependency

logger = logging.getLogger(__name__)


async def _get_job_demand_analytics_repository(
    job_repository: IJobRepository = Depends(get_job_repository),
) -> IJobDemandAnalyticsRepository:
    # Reuses the same matching-service-backed IJobRepository as the Job
    # Postings tab so the chart stays consistent with what users browse.
    return JobDemandAnalyticsRepository(job_repository)


def add_job_demand_analytics_routes(router: APIRouter, auth: Authentication) -> None:
    """Register job-demand analytics routes on the given router."""
    # Fail fast at startup: a missing/malformed sector_category_map.json should
    # break the deploy here, not surface as a 500 on the first user request.
    validate_sector_map()

    @router.get(
        path="/job-demand-stats",
        response_model=JobDemandStatsResponse,
        responses={
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        description=(
            "Aggregate the top in-demand skills across job postings. Optionally "
            "filter by location (province) and sector (institution sector mapped "
            "to job-category prefixes). This is an independent job-side market "
            "signal, not derived from per-user matching. Requires a valid access "
            "role (results are global — jobs are not institution-scoped, so no "
            "institution scoping is applied)."
        ),
    )
    async def _job_demand_stats(
        # Role-gated like the sibling skill_gap/skills_supply routes; no
        # institution scoping (jobs are global). Unused -> underscore name.
        _access_role: AccessRole = Depends(get_access_role_dependency(auth)),
        limit: Annotated[
            int,
            Query(ge=1, le=100, description="Maximum number of top in-demand skills to return."),
        ] = 10,
        location: Optional[str] = Query(
            default=None,
            max_length=120,
            description="Filter by province/location (job.location)",
        ),
        sector: Optional[str] = Query(
            default=None,
            max_length=120,
            description="Filter by institution sector (mapped to job-category prefixes)",
        ),
        repo: IJobDemandAnalyticsRepository = Depends(_get_job_demand_analytics_repository),
    ) -> JobDemandStatsResponse:
        try:
            return await repo.get_job_demand_stats(limit, location=location, sector=sector)
        except Exception as e:
            logger.exception(e)
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Unexpected error"
            ) from e
