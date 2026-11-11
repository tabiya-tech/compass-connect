import asyncio
import logging
import time

import google.auth
import google.auth.exceptions
import google.auth.jwt
import google.auth.transport.requests
import google.oauth2.id_token


class IdTokenError(Exception):
    """Raised when a Google ID token cannot be fetched."""


class GoogleIdTokenProvider:
    """
    Fetches Google ID tokens for calling a Cloud Run service that requires authentication (roles/run.invoker).

    The token is cached and refreshed shortly before it expires (Google ID tokens are valid for one hour).
    """

    _REFRESH_MARGIN_SECONDS = 300

    def __init__(self, *, audience: str):
        self._audience = audience
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()
        self._logger = logging.getLogger(self.__class__.__name__)

    async def get_token(self) -> str:
        if self._is_valid():
            return self._token
        async with self._lock:
            if self._is_valid():
                return self._token
            try:
                # google-auth is synchronous, do not block the event loop.
                token = await asyncio.to_thread(_fetch_id_token, self._audience)
                expires_at = float(google.auth.jwt.decode(token, verify=False)["exp"])
            except Exception as e:  # pylint: disable=broad-except
                raise IdTokenError(f"Failed to fetch an ID token for {self._audience}: {e}") from e
            self._token, self._expires_at = token, expires_at
            return token

    def _is_valid(self) -> bool:
        return self._token is not None and time.time() < self._expires_at - self._REFRESH_MARGIN_SECONDS


def _fetch_id_token(audience: str) -> str:
    request = google.auth.transport.requests.Request()
    try:
        # Service account credentials: the metadata server on Cloud Run, or GOOGLE_APPLICATION_CREDENTIALS.
        return google.oauth2.id_token.fetch_id_token(request, audience)
    except google.auth.exceptions.DefaultCredentialsError:
        # Local development with user credentials (gcloud auth application-default login). Their ID token is not
        # issued for the audience, but Cloud Run accepts it for users that have roles/run.invoker.
        credentials, _ = google.auth.default()
        credentials.refresh(request)
        token = getattr(credentials, "id_token", None)
        if not token:
            raise
        return token
