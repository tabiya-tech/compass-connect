import json
import logging
import threading
import time
import urllib.request
from typing import Optional, Any

import jwt

logger = logging.getLogger(__name__)

_FIREBASE_JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
_FIREBASE_ISSUER_PREFIX = "https://securetoken.google.com/"
_JWKS_CACHE_SECONDS = 3600
_JWKS_MIN_REFETCH_SECONDS = 60
_JWKS_FETCH_TIMEOUT_SECONDS = 5
_TOKEN_CLOCK_SKEW_SECONDS = 30


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


def verify_firebase_id_token(token: str, project_id: str) -> dict:
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
