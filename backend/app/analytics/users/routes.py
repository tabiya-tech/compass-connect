import binascii
import logging
from http import HTTPStatus

from fastapi import APIRouter, Depends, Query

from app.analytics.users.repository import UserRepository, get_user_repository
from app.analytics.types import PaginatedListMeta, PaginatedListResponse, User
from app.constants.errors import HTTPErrorResponse
from app.users.auth import Authentication, ApiKeyAuth
from app.users.access_role import AccessRole, get_access_role_dependency, decode_institution_id

logger = logging.getLogger(__name__)


def _resolve_institution(institution: str | None) -> str | None:
    """
    Resolve the institution query param to an institution name.
    Callers are expected to pass the base64url-encoded institution id, the same way
    /analytics/reach does. A value that is not valid base64 is treated as a plain
    institution name, so external providers can also filter by name.
    """
    if not institution:
        return None
    try:
        return decode_institution_id(institution)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return institution


def add_users_routes(router: APIRouter, auth: Authentication, api_key_auth: ApiKeyAuth):
    @router.get(
        "",
        response_model=PaginatedListResponse[User],
        responses={HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse}, HTTPStatus.UNAUTHORIZED: {"model": HTTPErrorResponse}},
        description="List students with optional filters, search, and cursor-based pagination. Requires authentication.",
    )
    async def list_users(
        access_role: AccessRole = Depends(get_access_role_dependency(auth)),
        active: bool | None = Query(default=None, description="Filter by active status"),
        institution: str | None = Query(default=None, description="Filter by institution name"),
        province: str | None = Query(default=None, description="Filter by province"),
        programme: str | None = Query(default=None, description="Filter by programme"),
        year: str | None = Query(default=None, description="Filter by year of study"),
        search: str | None = Query(default=None, description="Search across institution, programme, and year"),
        cursor: str | None = Query(default=None, description="Pagination cursor from previous response"),
        limit: int = Query(default=20, ge=1, le=100, description="Max items per page"),
        include: str | None = Query(default=None, description="Comma-separated: 'count' to include total"),
        repository: UserRepository = Depends(get_user_repository),
    ):
        # Institution staff are scoped to their own institution; ignore any institution param they pass
        if access_role.is_institution_staff and access_role.institution_id:
            institution = decode_institution_id(access_role.institution_id)

        include_count = include and "count" in include.split(",")

        items, next_cursor_str, has_more = await repository.list_users(
            active=active,
            institution=institution,
            province=province,
            programme=programme,
            year=year,
            search=search,
            cursor=cursor,
            limit=limit,
        )
        total = await repository.count_users(
            active=active,
            institution=institution,
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

    @router.get(
        "/analytics",
        response_model=PaginatedListResponse[User],
        dependencies=[Depends(api_key_auth)],
        responses={
            HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse},
            HTTPStatus.UNAUTHORIZED: {"model": HTTPErrorResponse},
        },
        description=(
            "List students for external providers. Server-to-server endpoint authenticated with an "
            "x-api-key header; the caller resolves its own scope and passes it explicitly via the "
            "`institution` query parameter (base64url-encoded institution id or plain name). "
            "Omitting it returns students across all institutions."
        ),
    )
    async def list_public_users(
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
