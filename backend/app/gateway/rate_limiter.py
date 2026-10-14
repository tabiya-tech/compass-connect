import logging
import math
import time
from typing import Optional

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.gateway.ingress_mode import get_ingress_mode, IngressMode, get_rate_limit_per_minute, RATE_LIMIT_ENV_VAR

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60


class _Bucket:
    __slots__ = ("tokens", "updated_at", "limited")

    def __init__(self, tokens: float, updated_at: float):
        self.tokens = tokens
        self.updated_at = updated_at
        self.limited = False


class ClientRateLimiter:
    """
    A token bucket per client: a client can send up to `limit_per_minute` requests at once, and its bucket refills
    at `limit_per_minute` tokens per minute.
    The state lives in this process only: with several replicas, each replica counts separately.
    It is not thread-safe, it is meant to be used from the event loop (nothing is awaited while a bucket is updated).
    """

    def __init__(self, limit_per_minute: int):
        self._limit_per_minute = limit_per_minute
        self._refill_per_second = limit_per_minute / _WINDOW_SECONDS
        self._buckets: dict[str, _Bucket] = {}
        self._last_eviction = time.monotonic()

    def acquire(self, client: str) -> Optional[int]:
        """
        Takes a token for a request of the client.
        :param client: The key of the client, e.g. its IP.
        :return: None if the request is allowed, otherwise the number of seconds after which the client can retry.
        """
        now = time.monotonic()
        self._evict_idle_buckets(now)
        bucket = self._buckets.get(client)
        if bucket is None:
            bucket = self._buckets[client] = _Bucket(self._limit_per_minute, now)
        else:
            bucket.tokens = min(self._limit_per_minute, bucket.tokens + (now - bucket.updated_at) * self._refill_per_second)
            bucket.updated_at = now

        if bucket.tokens >= 1:
            bucket.tokens -= 1
            bucket.limited = False
            return None

        if not bucket.limited:
            # Log once when a client starts being limited, not for every rejected request.
            bucket.limited = True
            logger.warning("A client exceeded the rate limit of %d requests per minute", self._limit_per_minute)
        return max(1, math.ceil((1 - bucket.tokens) / self._refill_per_second))

    def _evict_idle_buckets(self, now: float) -> None:
        # A bucket idle for a whole window is full again, the same as a new one, so dropping it loses nothing.
        # This keeps the memory bounded by the number of clients seen in the last window.
        if now - self._last_eviction < _WINDOW_SECONDS:
            return
        self._last_eviction = now
        self._buckets = {client: bucket for client, bucket in self._buckets.items() if now - bucket.updated_at < _WINDOW_SECONDS}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that limits the number of requests per client IP, as the Google API Gateway does for the cloud deployments.
    Responds with 429 and a Retry-After header when the limit is exceeded.
    """

    def __init__(self, app, limit_per_minute: int):
        super().__init__(app)
        self._limiter = ClientRateLimiter(limit_per_minute)

    async def dispatch(self, request: Request, call_next):
        # The client host is the address of the peer, or the one uvicorn read from the X-Forwarded-For header sent by a
        # trusted proxy (FORWARDED_ALLOW_IPS). The header is not read here: when the backend is reached directly, anyone can forge it.
        client = request.client.host if request.client else "unknown"
        retry_after = self._limiter.acquire(client)
        if retry_after is not None:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests, please try again later."},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)


def add_rate_limiter(app: FastAPI) -> None:
    """
    Adds the rate limiter to the app when there is no API Gateway in front of the backend (INGRESS_MODE=direct).
    Behind the API Gateway, the gateway applies the rate limit.
    """
    if get_ingress_mode() != IngressMode.DIRECT:
        return
    limit_per_minute = get_rate_limit_per_minute()
    if limit_per_minute == 0:
        logger.warning("The rate limiter is disabled (%s=0)", RATE_LIMIT_ENV_VAR)
        return
    logger.info("Rate limiting the requests to %d per minute per client IP", limit_per_minute)
    app.add_middleware(RateLimitMiddleware, limit_per_minute=limit_per_minute)
