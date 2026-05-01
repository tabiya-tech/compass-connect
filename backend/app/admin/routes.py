from fastapi import APIRouter, Depends, HTTPException, status

from app.admin.users.routes import get_admin_users_routes
from app.users.auth import Authentication, UserInfo


def get_admin_routes(auth: Authentication):
    """
    Create and return the admin router with all admin sub-routes.
    All routes require the caller to have the 'admin' role.

    :return: APIRouter with all admin endpoints.
    """

    def require_admin(user_info: UserInfo = Depends(auth.get_user_info())) -> UserInfo:
        if user_info.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
        return user_info

    router = APIRouter(dependencies=[Depends(require_admin)])
    users = get_admin_users_routes()
    router.include_router(users, prefix="/users", tags=["Admin Users"])
    return router
