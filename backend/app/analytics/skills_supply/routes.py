"""
Skills supply analytics routes.
"""
import logging
from http import HTTPStatus
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.analytics.skills_supply.repository import (
    ISkillsSupplyAnalyticsRepository,
    SkillsSupplyAnalyticsRepository,
)
from app.analytics.skills_supply.types import SkillsSupplyStatsResponse
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


async def _get_skills_supply_repository(
    application_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_application_db),
) -> ISkillsSupplyAnalyticsRepository:
    return SkillsSupplyAnalyticsRepository(application_db)


def add_skills_supply_analytics_routes(router: APIRouter, auth: Authentication) -> None:
    @router.get(
        path="/skills-supply-stats",
        response_model=SkillsSupplyStatsResponse,
        responses={
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        description=(
            "Aggregate the most common skills identified by students during skills discovery. "
            "Institution staff are automatically scoped to their own institution. "
            "Province filter is admin-only. Sector filter applies to all roles."
        ),
    )
    async def _skills_supply_stats(
        limit: int = Query(default=10, ge=1, le=50, description="Number of top skills to return"),
        province: Optional[str] = Query(None, description="Filter by student province (admin only)."),
        sector: Optional[str] = Query(None, description="Filter by programme sector (e.g. Agriculture, Energy)."),
        access_role: AccessRole = Depends(get_access_role_dependency(auth)),
        repo: ISkillsSupplyAnalyticsRepository = Depends(_get_skills_supply_repository),
        userdata_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_userdata_db),
    ) -> SkillsSupplyStatsResponse:
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
            return await repo.get_skills_supply_stats(limit=limit, user_ids=user_ids)
        except Exception as e:
            logger.exception(e)
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Unexpected error"
            ) from e
