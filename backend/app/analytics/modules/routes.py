import logging
from datetime import date, datetime, time, timezone
from http import HTTPStatus
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.analytics.modules.repository import (
    JobReadinessAnalyticsRepository,
    ModuleAnalyticsRepository,
    get_module_analytics_repository,
)
from app.analytics.modules.types import (
    BuildYourProfileResponse,
    BuildYourProfileSeriesPoint,
    BuildYourProfileSummary,
    ConversationPhaseReach,
    JobReadinessResponse,
    JobsResponse,
    JobsSummary,
)
from app.constants.errors import HTTPErrorResponse
from app.jobs.get_job_service import get_job_service
from app.jobs.service import IJobService
from app.server_dependencies.db_dependencies import CompassDBProvider
from app.users.access_role import decode_institution_id
from app.users.auth import ApiKeyAuth

logger = logging.getLogger(__name__)

_api_key_auth = ApiKeyAuth()


def _decode_institution_ids(institution_ids: Optional[str]) -> Optional[list[str]]:
    if not institution_ids:
        return None
    return [decode_institution_id(encoded) for encoded in institution_ids.split(",") if encoded]


async def _get_job_readiness_repository(
    application_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_application_db),
    userdata_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_userdata_db),
) -> JobReadinessAnalyticsRepository:
    return JobReadinessAnalyticsRepository(application_db, userdata_db)


def add_module_analytics_routes(router: APIRouter) -> None:
    @router.get(
        "/modules/build-your-profile",
        response_model=BuildYourProfileResponse,
        dependencies=[Depends(_api_key_auth)],
        responses={
            HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse},
            HTTPStatus.UNAUTHORIZED: {"model": HTTPErrorResponse},
        },
        description="Build Your Profile module adoption summary and time series for the given scope.",
    )
    async def get_build_your_profile(
        start_date: date = Query(..., description="Start of date range, inclusive (yyyy-MM-dd)", examples=["YYYY-MM-DD"]),
        end_date: date = Query(..., description="End of date range, inclusive (yyyy-MM-dd)", examples=["YYYY-MM-DD"]),
        granularity: str = Query(default="day", description="Time bucket size: day | week | month"),
        institution_ids: Optional[str] = Query(
            default=None, description="Comma-separated, base64url-encoded institution ids to scope to"
        ),
        repository: ModuleAnalyticsRepository = Depends(get_module_analytics_repository),
    ) -> BuildYourProfileResponse:
        if start_date > end_date:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="start_date must be before or equal to end_date",
            )
        if granularity not in ("day", "week", "month"):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="granularity must be 'day', 'week' or 'month'",
            )

        institution_names = _decode_institution_ids(institution_ids)

        start_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, time.max).replace(tzinfo=timezone.utc)

        raw = await repository.get_build_your_profile(
            start_date=start_dt,
            end_date=end_dt,
            granularity=granularity,
            institution_names=institution_names,
        )
        return BuildYourProfileResponse(
            summary=BuildYourProfileSummary(**raw["summary"]),
            series=[BuildYourProfileSeriesPoint(**p) for p in raw["series"]],
            phases=[ConversationPhaseReach(**p) for p in raw["phases"]],
        )

    @router.get(
        "/modules/job-readiness",
        response_model=JobReadinessResponse,
        dependencies=[Depends(_api_key_auth)],
        responses={
            HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse},
            HTTPStatus.UNAUTHORIZED: {"model": HTTPErrorResponse},
        },
        description=(
            "Job Readiness (career readiness) module analytics for the compass-analytics dashboard. "
            "Server-to-server endpoint authenticated with an x-api-key header. "
            "Pass institution_ids as a comma-separated list of base64url-encoded institution IDs "
            "to scope to a subset; omit to return all institutions."
        ),
    )
    async def get_job_readiness(
        institution_ids: Optional[str] = Query(
            default=None,
            description="Comma-separated base64url-encoded institution IDs; omit for all",
        ),
        repository: JobReadinessAnalyticsRepository = Depends(_get_job_readiness_repository),
    ) -> JobReadinessResponse:
        institution_names: Optional[list[str]] = None
        if institution_ids:
            institution_names = []
            for encoded_id in institution_ids.split(","):
                encoded_id = encoded_id.strip()
                if not encoded_id:
                    continue
                try:
                    institution_names.append(decode_institution_id(encoded_id))
                except Exception:  # pylint: disable=broad-except
                    logger.warning("Could not decode institution_id: %s", encoded_id)

        try:
            return await repository.get_job_readiness(institution_names or None)
        except Exception as exc:
            logger.exception(exc)
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Unexpected error fetching job readiness analytics",
            ) from exc

    @router.get(
        "/modules/jobs",
        response_model=JobsResponse,
        dependencies=[Depends(_api_key_auth)],
        responses={HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse}},
        description="Jobs module summary — jobs currently in the classifier feed.",
    )
    async def get_jobs_module(
        job_service: IJobService = Depends(get_job_service),
    ) -> JobsResponse:
        try:
            stats = await job_service.get_job_stats()
        except Exception as exc:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Failed to fetch job stats",
            ) from exc
        return JobsResponse(summary=JobsSummary(jobs_sourced=stats.total))


# Alias kept for callers that registered the old name before this module was extended.
add_modules_analytics_routes = add_module_analytics_routes
