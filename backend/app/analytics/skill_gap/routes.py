"""
Skill gap analytics routes.
"""
import logging
from http import HTTPStatus
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.analytics.skill_gap.repository import (
    ISkillGapAnalyticsRepository,
    SkillGapAnalyticsRepository,
)
from app.analytics.skill_gap.types import SkillGapStatsResponse
from app.analytics.user_filter import (
    resolve_user_ids_for_institution,
    resolve_user_ids_for_province,
    resolve_user_ids_for_sector,
    intersect_user_id_sets,
)
from app.constants.errors import HTTPErrorResponse
from app.server_dependencies.db_dependencies import CompassDBProvider
from app.users.auth import Authentication
from app.users.access_role import AccessRole, get_access_role_dependency, decode_institution_id

logger = logging.getLogger(__name__)


async def _get_skill_gap_analytics_repository(
    application_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_application_db),
) -> ISkillGapAnalyticsRepository:
    return SkillGapAnalyticsRepository(application_db)


def add_skill_gap_analytics_routes(router: APIRouter, auth: Authentication) -> None:
    """Register skill gap analytics routes on the given router."""

    @router.get(
        path="/skill-gap-stats",
        response_model=SkillGapStatsResponse,
        responses={
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        description=(
            "Aggregate skill gap statistics across students with pre-computed recommendations. "
            "Institution staff are automatically scoped to their own institution. "
            "Province filter is admin-only. Sector filter applies to all roles."
        ),
    )
    async def _skill_gap_stats(
        limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of top skill gaps to return.")] = 10,
        province: Optional[str] = Query(None, description="Filter by student province (admin only)."),
        sector: Optional[str] = Query(None, description="Filter by programme sector (e.g. Agriculture, Energy)."),
        access_role: AccessRole = Depends(get_access_role_dependency(auth)),
        repo: ISkillGapAnalyticsRepository = Depends(_get_skill_gap_analytics_repository),
        userdata_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_userdata_db),
    ) -> SkillGapStatsResponse:
        try:
            user_id_sets: list[list[str]] = []

            if access_role.is_institution_staff and access_role.institution_id:
                institution_name = decode_institution_id(access_role.institution_id)
                user_id_sets.append(await resolve_user_ids_for_institution(institution_name, userdata_db))

            if province and not access_role.is_institution_staff:
                user_id_sets.append(await resolve_user_ids_for_province(province, userdata_db))

            if sector:
                user_id_sets.append(await resolve_user_ids_for_sector(sector, userdata_db))

            user_ids = intersect_user_id_sets(user_id_sets)
            return await repo.get_skill_gap_stats(limit, user_ids=user_ids)
        except Exception as e:
            logger.exception(e)
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Unexpected error"
            ) from e
