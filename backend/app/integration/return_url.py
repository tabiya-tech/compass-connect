"""
The return URL: where Compass sends a user created by another platform when they are done. Only origins in the
instance's allow-list are accepted, so a key holder cannot make Compass send users to any site (open redirect).
"""

from typing import Optional
from urllib.parse import urlsplit


class InvalidReturnUrlError(Exception):
    """
    The return URL is malformed, not https, or its origin is not allowed. The message says which, for the caller.
    """


def _origin(url: str) -> Optional[str]:
    """
    The origin of an absolute http(s) URL in lowercase, or None. URLs with credentials have none:
    `https://allowed.org@other.org` reads as allowed.org to a person.
    """
    try:
        parts = urlsplit(url.strip())
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or "@" in parts.netloc:
        return None
    return f"{parts.scheme.lower()}://{parts.hostname}{port}"


def validate_return_url(url: str, allowed_origins: list[str]) -> None:
    """
    :param allowed_origins: as configured, e.g. ["https://partner.example.org"]
    :raises InvalidReturnUrlError: unless the URL is https (http only on localhost) and its origin is allowed
    """
    origin = _origin(url)
    if origin is None:
        raise InvalidReturnUrlError("return_url must be an absolute https URL.")
    if origin.startswith("http://") and urlsplit(origin).hostname not in ("localhost", "127.0.0.1"):
        raise InvalidReturnUrlError("return_url must use https (http only for localhost).")
    if origin not in {_origin(allowed) for allowed in allowed_origins}:
        raise InvalidReturnUrlError("return_url is not allowed on this instance.")
