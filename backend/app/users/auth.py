import base64
import hmac
import logging
import json
import os
import threading
import time
import urllib.request
from enum import Enum
from typing import Optional, Callable, Any

import jwt

from pydantic import BaseModel
from fastapi import Depends, Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader

logger = logging.getLogger(__name__)

SELF_HOSTED_ENVIRONMENT_TYPE = "selfhosted"
"""
The value of TARGET_ENVIRONMENT_TYPE for deployments that run without the Google API Gateway
(on any cloud provider or on-premise). In this mode the backend verifies the Firebase ID tokens itself
and validates the API keys itself.
"""

_FIREBASE_JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
_FIREBASE_ISSUER_PREFIX = "https://securetoken.google.com/"
_JWKS_CACHE_SECONDS = 3600
_JWKS_MIN_REFETCH_SECONDS = 60
_JWKS_FETCH_TIMEOUT_SECONDS = 5
_TOKEN_CLOCK_SKEW_SECONDS = 30


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


def _decode_user_info_api_gateway(auth_info_b64):
    """
    Decodes a base64-encoded string containing user information and returns it as a dictionary.
    The api-gateway does not allways send the correct padding, so this function
    handles partial padding (missing one or two `=` characters). Rejects invalid input.

    Args:
        auth_info_b64 (str): The base64-encoded string containing JSON user data.

    Returns:
        dict: Decoded user information as a Python dictionary.

    Raises:
        ValueError: If the input is not valid base64 or if the JSON is invalid.
    """
    try:
        # Check if padding is needed and apply it
        padding_needed = len(auth_info_b64) % 4
        if padding_needed == 1:
            raise ValueError("Invalid base64 input: length is not compatible with base64 encoding")
        elif padding_needed == 2:
            padded_base64 = auth_info_b64 + '=='  # Add two `=` characters
        elif padding_needed == 3:
            padded_base64 = auth_info_b64 + '='  # Add one `=` character
        else:
            padded_base64 = auth_info_b64  # No padding needed

        # Decode the base64 string
        decoded_bytes = base64.b64decode(padded_base64.encode('utf-8'))

        # Convert bytes to string
        decoded_string = decoded_bytes.decode('utf-8')

        # Parse JSON from the decoded string
        user_info = json.loads(decoded_string)

        return user_info

    except Exception as e:
        raise ValueError("Invalid base64 or JSON input") from e


class _FirebasePublicKeys:
    """
    Provides the public keys Google uses to sign the Firebase ID tokens, fetched from the Google JWKS endpoint.
    The keys are cached for _JWKS_CACHE_SECONDS. A (re-)fetch is attempted at most once per _JWKS_MIN_REFETCH_SECONDS,
    whether it is triggered by an expired cache or an unknown key id, so a caller sending random key ids (or an
    unreachable Google endpoint) cannot make every request wait for the network. If a refresh fails, the keys already
    cached keep being used.
    """

    def __init__(self, jwks_url: str = _FIREBASE_JWKS_URL):
        self._jwks_url = jwks_url
        self._keys: dict[str, Any] = {}
        self._fetched_at: float = 0
        self._last_attempt: Optional[float] = None
        self._lock = threading.Lock()

    def _fetch(self) -> None:
        with urllib.request.urlopen(self._jwks_url, timeout=_JWKS_FETCH_TIMEOUT_SECONDS) as response:  # nosec B310 - fixed https URL
            jwks = json.loads(response.read())
        self._keys = {key.key_id: key.key for key in jwt.PyJWKSet.from_dict(jwks).keys}
        self._fetched_at = time.monotonic()

    def get_key(self, key_id: str) -> Any:
        with self._lock:
            now = time.monotonic()
            needs_refresh = self._fetched_at == 0 or now - self._fetched_at > _JWKS_CACHE_SECONDS or key_id not in self._keys
            may_attempt = self._last_attempt is None or now - self._last_attempt > _JWKS_MIN_REFETCH_SECONDS
            if needs_refresh and may_attempt:
                self._last_attempt = now
                try:
                    self._fetch()
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning("Could not fetch the Firebase public keys: %s - %s", e.__class__.__name__, e)
            if key_id not in self._keys:
                raise jwt.InvalidTokenError("Unknown signing key id")
            return self._keys[key_id]


_firebase_public_keys = _FirebasePublicKeys()


def _verify_firebase_id_token(token: str, project_id: str) -> dict:
    """
    Verifies a Firebase ID token the same way the Google API Gateway does for the cloud deployments:
    RS256 signature against Google's public keys, not expired, audience == project id,
    and issuer == https://securetoken.google.com/<project id>.
    :param token: The encoded ID token.
    :param project_id: The Firebase project id the token must have been issued for.
    :return: The verified claims.
    :raises jwt.InvalidTokenError: if the token is not valid.
    """
    header = jwt.get_unverified_header(token)
    if header.get("alg") != "RS256" or not header.get("kid"):
        raise jwt.InvalidTokenError("Unexpected token algorithm or missing key id")
    claims = jwt.decode(
        token,
        key=_firebase_public_keys.get_key(header["kid"]),
        algorithms=["RS256"],
        audience=project_id,
        issuer=_FIREBASE_ISSUER_PREFIX + project_id,
        leeway=_TOKEN_CLOCK_SKEW_SECONDS,  # the clock of the host may be a few seconds behind Google's (iat/exp)
        options={"require": ["exp", "iat", "sub", "aud", "iss"]},
    )
    if not claims["sub"]:
        raise jwt.InvalidTokenError("Empty subject")
    return claims


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
            target_env = os.getenv("TARGET_ENVIRONMENT_TYPE")
            try:
                credentials: str = provider.credentials
                token_info: Any
                if target_env == SELF_HOSTED_ENVIRONMENT_TYPE:
                    # There is no API Gateway in front of the backend, so we verify the Firebase ID token ourselves.
                    # The `x-apigateway-api-userinfo` header is deliberately ignored: anyone who can reach the backend could forge it.
                    project_id = os.getenv("FIREBASE_PROJECT_ID")
                    if not credentials or not project_id:
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
                    token_info = _verify_firebase_id_token(credentials, project_id)
                elif target_env != "local":
                    # When deployed, the credentials are verified by the API Gateway, which sends
                    # the decoded user information in a Base64-encoded format through the `x-apigateway-api-userinfo` header.
                    # If the header is missing, the user should be treated as unauthenticated, and a 403 error must be raised.
                    # While this scenario should not occur under normal circumstances, since the
                    # API Gateway is expected to always include the header, we implement this check
                    # as a precautionary measure. For example, such an issue could arise if the API
                    # Gateway is improperly configured or if the incoming request does not originate
                    # from the API Gateway.
                    auth_info_b64 = request.headers.get('x-apigateway-api-userinfo')
                    if not auth_info_b64:
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="forbidden")

                    # The user info is encoded as base 64 string by the api-gateway
                    token_info = _decode_user_info_api_gateway(auth_info_b64)
                else:
                    # When running locally, use the jwt token from Authorization header.
                    if not credentials:
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized, missing credentials")
                    # Decode the token without verifying the signature as we are running locally.
                    token_info = jwt.decode(credentials, options={"verify_signature": False})
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
        if os.getenv("TARGET_ENVIRONMENT_TYPE") == SELF_HOSTED_ENVIRONMENT_TYPE:
            # There is no API Gateway to validate the key, so we validate it against the configured API_KEYS
            # (comma separated). If none are configured, the API key endpoints are disabled.
            valid_keys = [key.strip() for key in os.getenv("API_KEYS", "").split(",") if key.strip()]
            # Compare against all the keys (no early exit) in constant time.
            matches = [hmac.compare_digest(api_key.encode(), valid_key.encode()) for valid_key in valid_keys]
            if not any(matches):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        # Otherwise the API Gateway validates the key.
        return api_key
