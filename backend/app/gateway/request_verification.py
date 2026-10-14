import os

import jwt
from fastapi import Request, HTTPException, status

from app.gateway.api_keys import is_configured_api_key
from app.gateway.firebase_tokens import verify_firebase_id_token
from app.gateway.google_api_gateway import decode_user_info_header
from app.gateway.ingress_mode import get_ingress_mode, IngressMode


def get_token_claims(request: Request, credentials: str) -> dict:
    """
    Returns the claims of the Firebase ID token of the request, verified according to the ingress mode.
    :param request: The request.
    :param credentials: The bearer token of the Authorization header.
    :return: The claims of the token.
    :raises HTTPException: 401 if the request is not authenticated.
    :raises Exception: if the token or the gateway header is not valid (jwt.InvalidTokenError, ValueError, ...).
    """
    if get_ingress_mode() == IngressMode.DIRECT:
        # There is no API Gateway in front of the backend, so we verify the Firebase ID token ourselves.
        # The `x-apigateway-api-userinfo` header is deliberately ignored: anyone who can reach the backend could forge it.
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        if not credentials or not project_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
        return verify_firebase_id_token(credentials, project_id)

    if os.getenv("TARGET_ENVIRONMENT_TYPE") == "local":
        # When running locally there is no API Gateway, use the jwt token from Authorization header.
        if not credentials:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized, missing credentials")
        # Decode the token without verifying the signature as we are running locally.
        return jwt.decode(credentials, options={"verify_signature": False})

    # When deployed, the credentials are verified by the API Gateway, which sends
    # the decoded user information in a Base64-encoded format through the `x-apigateway-api-userinfo` header.
    return decode_user_info_header(request)


def check_api_key(api_key: str) -> None:
    """
    Checks the key sent in the `x-api-key` header according to the ingress mode.
    :param api_key: The key.
    :raises HTTPException: 403 if the key is not accepted.
    """
    if get_ingress_mode() == IngressMode.DIRECT:
        # There is no API Gateway to validate the key, so we validate it against the configured API_KEYS.
        # If none are configured, the API key endpoints are disabled.
        if not is_configured_api_key(api_key):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    # Otherwise the API Gateway validates the key.
