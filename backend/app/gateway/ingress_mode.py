import os
from enum import Enum

INGRESS_MODE_ENV_VAR = "INGRESS_MODE"
RATE_LIMIT_ENV_VAR = "BACKEND_RATE_LIMIT_PER_MINUTE"
DEFAULT_RATE_LIMIT_PER_MINUTE = 600


class IngressMode(Enum):
    """
    How the requests reach the backend, set with the INGRESS_MODE env variable.
    """
    GATEWAY = "gateway"
    """
    Behind the Google API Gateway (the default, used by the cloud deployments). The gateway verifies the Firebase ID tokens
    and the API keys, and applies the rate limit.
    """

    DIRECT = "direct"
    """
    Without a gateway in front (on any cloud provider or on-premise). The backend verifies the Firebase ID tokens
    and the API keys itself, and applies the rate limit.
    """


def get_ingress_mode() -> IngressMode:
    """
    :return: The ingress mode set in INGRESS_MODE, IngressMode.GATEWAY when it is not set.
    :raises ValueError: if INGRESS_MODE has an unknown value.
    """
    value = (os.getenv(INGRESS_MODE_ENV_VAR) or IngressMode.GATEWAY.value).strip().lower()
    try:
        return IngressMode(value)
    except ValueError:
        raise ValueError(f"Invalid {INGRESS_MODE_ENV_VAR} env variable: {value!r}. "
                         f"Allowed values: {', '.join(mode.value for mode in IngressMode)}") from None


def get_rate_limit_per_minute() -> int:
    """
    :return: The number of requests per minute allowed per client IP when the ingress mode is DIRECT, 0 to disable the rate limiter.
    :raises ValueError: if BACKEND_RATE_LIMIT_PER_MINUTE is not an integer >= 0.
    """
    value = os.getenv(RATE_LIMIT_ENV_VAR, "").strip()
    if not value:
        return DEFAULT_RATE_LIMIT_PER_MINUTE
    try:
        limit = int(value)
    except ValueError:
        limit = -1
    if limit < 0:
        raise ValueError(f"Invalid {RATE_LIMIT_ENV_VAR} env variable: {value!r}. "
                         f"Set it to the number of requests per minute allowed per client IP, or 0 to disable the rate limiter.")
    return limit


def validate_ingress_config() -> None:
    """
    Checks, at start-up, that the env variables needed by the ingress mode are set and valid.
    :raises ValueError: if they are not.
    """
    if get_ingress_mode() != IngressMode.DIRECT:
        return
    if not os.getenv("FIREBASE_PROJECT_ID"):
        raise ValueError(f"Mandatory FIREBASE_PROJECT_ID env variable is not set! It is required when {INGRESS_MODE_ENV_VAR} is "
                         f"'{IngressMode.DIRECT.value}' as the backend verifies the Firebase ID tokens itself "
                         f"(set it to the id of your Firebase project).")
    get_rate_limit_per_minute()
