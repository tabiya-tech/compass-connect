import asyncio
import base64
import logging
from http import HTTPStatus
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.analytics.institutions.repository import InstitutionRepository, get_institution_repository
from app.analytics.institutions.types import InstitutionSummary, InstitutionsResponse
from app.analytics.types import Institution, InstitutionFilterOptions, PaginatedListMeta, PaginatedListResponse
from app.constants.errors import HTTPErrorResponse
from app.server_dependencies.database_collections import Collections
from app.server_dependencies.db_dependencies import CompassDBProvider
from app.users.auth import ApiKeyAuth, Authentication, UserInfo
from app.users.access_role import decode_institution_id

logger = logging.getLogger(__name__)


_api_key_auth = ApiKeyAuth()


def add_institutions_routes(router: APIRouter, auth: Authentication):
    @router.get(
        "/institutions",
        response_model=PaginatedListResponse[Institution],
        responses={HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse}, HTTPStatus.UNAUTHORIZED: {"model": HTTPErrorResponse}},
        description="List institutions with optional filters and cursor-based pagination. Requires authentication.",
    )
    async def list_institutions(
        user_info: UserInfo = Depends(auth.get_user_info()),
        active: bool | None = Query(default=None, description="Filter by active status"),
        province: str | None = Query(default=None, description="Filter by province"),
        page: int | None = Query(default=None, description="1-based page number"),
        cursor: str | None = Query(default=None, description="Pagination cursor from previous response"),
        limit: int = Query(default=20, ge=1, le=100, description="Max items per page"),
        sort_by: Optional[
            Literal[
                "name",
                "students",
                "active_7_days",
                "skills_discovery_started_pct",
                "skills_discovery_completed_pct",
                "career_readiness_started_pct",
                "career_readiness_completed_pct",
                "career_explorer_started_pct",
            ]
        ] = Query(default=None, description="Sort field; omit for canonical institution order"),
        sort_dir: Literal["asc", "desc"] = Query(default="asc", description="Sort direction (used when sort_by is set)"),
        include: str | None = Query(default=None, description="Comma-separated: 'count' to include total"),
        repository: InstitutionRepository = Depends(get_institution_repository),
    ):
        include_count = bool(include and "count" in include.split(","))
        effective_cursor = cursor

        if page is not None:
            if page < 1:
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid page")
            offset = (page - 1) * limit
            effective_cursor = base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")
            include_count = True

        items, next_cursor_str, has_more = await repository.list_institutions(
            active=active,
            province=province,
            cursor=effective_cursor,
            limit=limit,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        total = await repository.count_institutions(
            active=active,
            province=province,
        ) if include_count else None

        meta = PaginatedListMeta(
            limit=limit,
            next_cursor=next_cursor_str,
            has_more=has_more,
            total=total if include_count else None,
        )
        return PaginatedListResponse(data=items, meta=meta)

    @router.get(
        "/institutions/filter-options",
        response_model=InstitutionFilterOptions,
        responses={HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse}},
        description="Return distinct province and sector values across all institutions.",
    )
    async def get_institution_filter_options(
        user_info: UserInfo = Depends(auth.get_user_info()),
        application_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_application_db),
    ) -> InstitutionFilterOptions:
        try:
            coll = application_db.get_collection(Collections.INSTITUTIONS)
            names_raw, provinces_raw, sectors_raw = await asyncio.gather(
                coll.distinct("name"),
                coll.distinct("province"),
                coll.distinct("sectors_covered"),
            )
            _exclude = {"all sectors", "all provinces", "all"}
            institution_names = sorted(n for n in names_raw if n and isinstance(n, str))
            provinces = sorted(p for p in provinces_raw if p and isinstance(p, str) and p.lower() not in _exclude)
            sectors = sorted(s for s in sectors_raw if s and isinstance(s, str) and s.lower() not in _exclude)
            return InstitutionFilterOptions(institution_names=institution_names, provinces=provinces, sectors=sectors)
        except Exception as e:
            logger.exception(e)
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Unexpected error"
            ) from e

    @router.get(
        "/institutions/summary",
        response_model=InstitutionsResponse,
        dependencies=[Depends(_api_key_auth)],
        responses={HTTPStatus.UNAUTHORIZED: {"model": HTTPErrorResponse}},
        description=(
            "Per-institution analytics summary for the compass-analytics dashboard. "
            "Server-to-server endpoint authenticated with an x-api-key header. "
            "Pass institution_ids as a comma-separated list of base64url-encoded institution IDs "
            "to scope to a subset; omit to return all institutions."
        ),
    )
    async def get_institutions_summary(
        institution_ids: Optional[str] = Query(
            default=None,
            description="Comma-separated base64url-encoded institution IDs to scope to; omit for all",
        ),
        repository: InstitutionRepository = Depends(get_institution_repository),
    ) -> InstitutionsResponse:
        # Decode the CSV institution_ids to names, which is the key used internally.
        requested_names: Optional[set[str]] = None
        if institution_ids:
            requested_names = set()
            for encoded_id in institution_ids.split(","):
                encoded_id = encoded_id.strip()
                if encoded_id:
                    try:
                        requested_names.add(decode_institution_id(encoded_id))
                    except Exception:  # pylint: disable=broad-except
                        logger.warning("Could not decode institution_id: %s", encoded_id)

        all_items, _, _ = await repository.list_institutions(names=requested_names)

        summaries = []
        for inst in all_items:
            summaries.append(InstitutionSummary(
                institution_id=inst.id,
                institution_name=inst.name,
                registered_users=inst.students or 0,
                active_users_7d=inst.active_7_days or 0,
                skills_discovery_started_pct=inst.skills_discovery_started_pct,
                skills_discovery_completed_pct=inst.skills_discovery_completed_pct,
                career_readiness_started_pct=inst.career_readiness_started_pct,
                career_readiness_completed_pct=inst.career_readiness_completed_pct,
                career_explorer_started_pct=inst.career_explorer_started_pct,
            ))

        return InstitutionsResponse(institutions=summaries)
