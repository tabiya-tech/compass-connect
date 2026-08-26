import logging
from datetime import date
from http import HTTPStatus
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.analytics.demographics.repository import DemographicsRepository, get_demographics_repository
from app.analytics.demographics.types import DemographicChart
from app.constants.errors import HTTPErrorResponse
from app.users.access_role import decode_institution_id
from app.users.auth import ApiKeyAuth

logger = logging.getLogger(__name__)

_api_key_auth = ApiKeyAuth()


def _decode_institution_ids(institution_ids: Optional[str]) -> Optional[list[str]]:
    if not institution_ids:
        return None
    return [decode_institution_id(encoded) for encoded in institution_ids.split(",") if encoded]


def add_demographics_routes(router: APIRouter):
    @router.get(
        "/demographics",
        response_model=list[DemographicChart],
        dependencies=[Depends(_api_key_auth)],
        responses={
            HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse},
            HTTPStatus.UNAUTHORIZED: {"model": HTTPErrorResponse},
        },
        description=(
            "Demographic breakdown (gender, region) for the given scope. Server-to-server "
            "endpoint authenticated with an x-api-key header; institution scope is passed "
            "explicitly by the caller via the `institution_ids` query parameter, or omitted "
            "for every institution. start_date/end_date/granularity are accepted and "
            "validated for an upcoming date-scoped demographics feature — today's response "
            "is a current snapshot regardless of the range given."
        ),
    )
    async def get_demographics(
        start_date: date = Query(..., description="Inclusive start of the reporting window (yyyy-MM-dd)"),
        end_date: date = Query(..., description="Inclusive end of the reporting window (yyyy-MM-dd)"),
        granularity: str = Query(default="day", description="Time bucket size: day | week | month"),
        institution_ids: Optional[str] = Query(
            default=None, description="Comma-separated, base64url-encoded institution ids to scope to"
        ),
        repository: DemographicsRepository = Depends(get_demographics_repository),
    ) -> list[DemographicChart]:
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

        raw = await repository.get_demographics(institution_names=institution_names)
        return [DemographicChart(**chart) for chart in raw]
