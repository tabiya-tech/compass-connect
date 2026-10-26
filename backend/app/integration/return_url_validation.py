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


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str) -> Optional[tuple[str, str, int]]:
    """
    The origin of an absolute http(s) URL as (scheme, host, port), lowercase and with the default port filled in, or
    None. A tuple, not a string: an IPv6 host loses its brackets, and `[::1]:8443` would read as the host `::1:8443`.
    URLs with credentials have none: `https://allowed.org@other.org` reads as allowed.org to a person.
    """
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        port = parts.port
    except ValueError:
        return None
    if scheme not in _DEFAULT_PORTS or not parts.hostname or "@" in parts.netloc:
        return None
    return scheme, parts.hostname, _DEFAULT_PORTS[scheme] if port is None else port


def validate_return_url(url: str, allowed_origins: list[str]) -> None:
    """
    :param allowed_origins: as configured, e.g. ["https://partner.example.org"]
    :raises InvalidReturnUrlError: unless the URL is https (http only on localhost) and its origin is allowed
    """
    origin = _origin(url)
    if origin is None:
        raise InvalidReturnUrlError("return_url must be an absolute https URL.")
    scheme, host, _ = origin
    if scheme == "http" and host not in ("localhost", "127.0.0.1"):
        raise InvalidReturnUrlError("return_url must use https (http only for localhost).")
    if origin not in {_origin(allowed) for allowed in allowed_origins}:
        raise InvalidReturnUrlError("return_url is not allowed on this instance.")
