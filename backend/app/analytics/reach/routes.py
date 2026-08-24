import logging
from datetime import date, datetime, time, timezone
from http import HTTPStatus
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.analytics.reach.repository import ReachRepository, get_reach_repository
from app.analytics.reach.types import ReachResponse, ReachSummary, TimeSeriesPoint
from app.constants.errors import HTTPErrorResponse
from app.users.access_role import decode_institution_id
from app.users.auth import ApiKeyAuth

logger = logging.getLogger(__name__)

# Reach is a server-to-server endpoint: the compass-analytics backend (which has
# already resolved the caller's role/scope) calls it with an API key, the same way
# the esco search routes are protected. The API Gateway validates the actual key;
# ApiKeyAuth only enforces that the x-api-key header is present.
_api_key_auth = ApiKeyAuth()


def add_reach_routes(router: APIRouter):
    @router.get(
        "/reach",
        response_model=ReachResponse,
        dependencies=[Depends(_api_key_auth)],
        responses={
            HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse},
            HTTPStatus.UNAUTHORIZED: {"model": HTTPErrorResponse},
        },
        description=(
            "Reach summary and daily time series for the given scope. Server-to-server "
            "endpoint authenticated with an x-api-key header; institution scope is passed "
            "explicitly by the caller via the `institution` query parameter."
        ),
    )
    async def get_reach(
        start_date: date = Query(..., description="Start of date range (inclusive)", examples=["YYYY-MM-DD"]),
        end_date: date = Query(..., description="End of date range (inclusive)", examples=["YYYY-MM-DD"]),
        granularity: str = Query(default="day", description="Time bucket size: day | week | month"),
        institution: Optional[str] = Query(default=None, description="Institution id to scope to"),
        repository: ReachRepository = Depends(get_reach_repository),
    ) -> ReachResponse:
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

        # The caller (compass-analytics) resolves the caller's scope and passes the
        # institution id explicitly. None means all institutions.
        institution_name: Optional[str] = decode_institution_id(institution) if institution else None

        start_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, time.max).replace(tzinfo=timezone.utc)

        raw = await repository.get_reach(
            start_date=start_dt,
            end_date=end_dt,
            institution_name=institution_name,
        )
        return ReachResponse(
            summary=ReachSummary(**raw["summary"]),
            series=[TimeSeriesPoint(**p) for p in raw["series"]],
        )
