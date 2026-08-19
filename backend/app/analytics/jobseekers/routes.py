import binascii
import logging
from http import HTTPStatus

from fastapi import APIRouter, Depends, Query

from app.analytics.types import PaginatedListMeta, PaginatedListResponse, User
from app.analytics.users.repository import UserRepository, get_user_repository
from app.constants.errors import HTTPErrorResponse
from app.users.access_role import decode_institution_id
from app.users.auth import ApiKeyAuth

logger = logging.getLogger(__name__)

_api_key_auth = ApiKeyAuth()


def _resolve_institution(institution: str | None) -> str | None:
    if not institution:
        return None
    try:
        return decode_institution_id(institution)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return institution


def add_job_seekers_routes(router: APIRouter):
    @router.get(
        "/jobseekers",
        response_model=PaginatedListResponse[User],
        dependencies=[Depends(_api_key_auth)],
        responses={
            HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse},
            HTTPStatus.UNAUTHORIZED: {"model": HTTPErrorResponse},
        }
    )
    async def list_job_seekers(
        active: bool | None = Query(default=None, description="Filter by active status"),
        institution: str | None = Query(default=None, description="Institution id or name to scope to"),
        province: str | None = Query(default=None, description="Filter by province"),
        programme: str | None = Query(default=None, description="Filter by programme"),
        year: str | None = Query(default=None, description="Filter by year of study"),
        search: str | None = Query(default=None, description="Search across institution, programme, and year"),
        cursor: str | None = Query(default=None, description="Pagination cursor from previous response"),
        limit: int = Query(default=20, ge=1, le=100, description="Max items per page"),
        include: str | None = Query(default=None, description="Comma-separated: 'count' to include total"),
        repository: UserRepository = Depends(get_user_repository),
    ):
        # The caller passes the institution explicitly; None means all institutions.
        institution_name = _resolve_institution(institution)

        include_count = include and "count" in include.split(",")

        items, next_cursor_str, has_more = await repository.list_users(
            active=active,
            institution=institution_name,
            province=province,
            programme=programme,
            year=year,
            search=search,
            cursor=cursor,
            limit=limit,
        )
        total = await repository.count_users(
            active=active,
            institution=institution_name,
            province=province,
            programme=programme,
            year=year,
            search=search,
        ) if include_count else None

        meta = PaginatedListMeta(
            limit=limit,
            next_cursor=next_cursor_str,
            has_more=has_more,
            total=total if include_count else None,
        )
        return PaginatedListResponse(data=items, meta=meta)
