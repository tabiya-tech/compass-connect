import logging
from datetime import date, datetime, time, timezone
from http import HTTPStatus
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.analytics.modules.repository import ModuleAnalyticsRepository, get_module_analytics_repository
from app.analytics.modules.types import (
    BuildYourProfileResponse,
    BuildYourProfileSeriesPoint,
    BuildYourProfileSummary,
    ConversationPhaseReach,
)
from app.constants.errors import HTTPErrorResponse
from app.users.access_role import decode_institution_id
from app.users.auth import ApiKeyAuth

logger = logging.getLogger(__name__)

_api_key_auth = ApiKeyAuth()


def _decode_institution_ids(institution_ids: Optional[str]) -> Optional[list[str]]:
    if not institution_ids:
        return None
    return [decode_institution_id(encoded) for encoded in institution_ids.split(",") if encoded]


def add_module_analytics_routes(router: APIRouter):
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

        # None means all institutions.
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
