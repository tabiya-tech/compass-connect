import logging
from enum import Enum
from typing import Optional, Callable, Any

from pydantic import BaseModel
from fastapi import Depends, Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader

from app.gateway.request_verification import get_token_claims, check_api_key

logger = logging.getLogger(__name__)


class SignInProvider(Enum):
    ANONYMOUS = "anonymous"
    PASSWORD = "password"  # nosec
    GOOGLE = "google.com"


class UserInfo(BaseModel):
    """
    This class is used to represent the user info.
    """
    user_id: str
    """
    The user id. This is the unique identifier for the user. We get it from idp (identity provider) like firebase.
    """

    name: Optional[str] = None
    """
    name of the user.
    It is optional because the user may not have a name. ie: Anonymous user.
    """

    email: Optional[str] = None

    token: str

    sign_in_provider: SignInProvider
    """
    Sign in Provider
    """

    role: Optional[str] = None
    """
    The user's access role, sourced from Firebase custom claims.
    e.g. 'admin' or 'institution_staff'. None for regular (student) users.
    """

    institution_id: Optional[str] = None
    """
    The institution ID, sourced from Firebase custom claims.
    Only set for institution_staff users.
    """

    class Config:
        extra = "forbid"


def _get_user_info(decoded_token: Any, token: str) -> UserInfo:
    """
    This function is used to get the user info from the decoded token.
    :param decoded_token: The decoded token.
    :param token: The token.
    :return: UserInfo object.
    """
    return UserInfo(
        user_id=decoded_token["sub"],
        name=decoded_token["name"] if "name" in decoded_token else None,  # Anon user will not have a name
        email=decoded_token["email"] if "email" in decoded_token else None,  # Anon user will not have an email
        token=token,
        sign_in_provider=decoded_token["firebase"]["sign_in_provider"],
        role=decoded_token.get("role"),
        institution_id=decoded_token.get("institutionId"),
    )


class Authentication:
    ############################################
    # Authentication
    ############################################
    """
    This class is responsible for managing the authentication of the users. It serves two main purposes:
    - Add the  security definitions for OpenAPI docs. We achieve on our api by using the HTTPBearer.
        To use you will need to add the function get_user_info in dependencies. If you don't want to get user info
        and just add only on the API docs you can use this class's object provider in the dependencies
        eg  `credentials = Depends(auth.provider)`
    - Get authenticated user. This is done by using the get_user_info
        function as a dependency in the route. the return value of this function is the user info.
    """
    provider: HTTPBearer
    """
    provider is an instance of HTTPBearer. It is used to add the security definitions for OpenAPI docs.
    """

    def __init__(self):
        # Currently one provider is supported, and it is the firebase scheme.
        self.provider = HTTPBearer(scheme_name="firebase")

    def get_user_info(self) -> Callable[[Request, HTTPAuthorizationCredentials], UserInfo]:
        """
        This function is a dependency that will be used to authenticate the user.
        Returns: UserInfo object.
        """

        def construct_user_info(request: Request, provider: HTTPAuthorizationCredentials = Depends(self.provider)) -> UserInfo:
            """
            This function is a dependency that will be used to authenticate the user.
            :param provider: provider auth provider.
            :param request: Request object.
            :return: UserInfo object.
            """
            try:
                credentials: str = provider.credentials
                # How the token is verified depends on the ingress mode, see app.gateway.
                token_info = get_token_claims(request, credentials)
                # decoded credentials.
                return _get_user_info(token_info, credentials)

            except HTTPException as e:
                raise e
            except Exception as e:
                # Log as warning as it is not clear if this is due to an unauthenticated request or some other "internal" reason.
                # Do not include any stack trace to avoid performance issues.
                logger.warning("Error while getting user info: %s - %s", e.__class__.__name__, e)
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

        return construct_user_info


class ApiKeyAuth:
    """
    This class is used to api calls using API keys in the header.
    see https://cloud.google.com/endpoints/docs/openapi/authentication-method for more details.
    """
    async def __call__(self, api_key: str = Depends(APIKeyHeader(scheme_name="gcp_api_key", name="x-api-key", auto_error=True))):
        # Since APIKeyHeader is used with auto_error=True, it will raise an exception if the header key is missing.
        # In the future, the key can be checked against roles and permissions.
        # Who validates the key depends on the ingress mode, see app.gateway.
        check_api_key(api_key)
        return api_key
