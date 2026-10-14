from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.gateway.rate_limiter as rate_limiter_module
from app.gateway.rate_limiter import ClientRateLimiter, RateLimitMiddleware, add_rate_limiter


@pytest.fixture(scope="function")
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """ A fake clock, moved forward by the tests. """
    current = [1000.0]
    monkeypatch.setattr(rate_limiter_module.time, "monotonic", lambda: current[0])
    return current


def _build_app(limit_per_minute: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit_per_minute=limit_per_minute)

    @app.get("/ping")
    def _ping():
        return {"ok": True}

    return app


class TestClientRateLimiter:
    def test_allows_the_limit_then_rejects_until_refilled(self, clock: list[float]):
        # GIVEN a limit of 60 requests per minute (1 token per second)
        limiter = ClientRateLimiter(60)

        # WHEN a client sends 60 requests at once
        # THEN they are all allowed
        for _ in range(60):
            assert limiter.acquire("1.1.1.1") is None

        # AND the next one is rejected, with the time after which the client can retry
        assert limiter.acquire("1.1.1.1") == 1

        # AND after a second, one more request is allowed, but not two
        clock[0] += 1
        assert limiter.acquire("1.1.1.1") is None
        assert limiter.acquire("1.1.1.1") == 1

    def test_retry_after_follows_the_refill_rate(self, clock: list[float]):
        # GIVEN a limit of 6 requests per minute (1 token every 10 seconds), used up
        limiter = ClientRateLimiter(6)
        for _ in range(6):
            limiter.acquire("1.1.1.1")

        # WHEN the client sends another request 4 seconds later
        clock[0] += 4

        # THEN it is rejected, and can retry when the next token is available
        assert limiter.acquire("1.1.1.1") == 6

    def test_clients_have_separate_limits(self, clock: list[float]):
        # GIVEN a client that used up its limit
        limiter = ClientRateLimiter(2)
        limiter.acquire("1.1.1.1")
        limiter.acquire("1.1.1.1")
        assert limiter.acquire("1.1.1.1") is not None

        # WHEN another client sends a request
        # THEN it is allowed
        assert limiter.acquire("2.2.2.2") is None

    def test_a_bucket_does_not_refill_above_the_limit(self, clock: list[float]):
        # GIVEN a client that has been idle for a long time
        limiter = ClientRateLimiter(3)
        limiter.acquire("1.1.1.1")
        clock[0] += 3600

        # WHEN it sends a burst of requests
        results = [limiter.acquire("1.1.1.1") for _ in range(4)]

        # THEN only the limit is allowed
        assert results[:3] == [None, None, None]
        assert results[3] is not None

    def test_idle_buckets_are_evicted(self, clock: list[float]):
        # GIVEN a client that sent a request, then was idle for more than a minute
        limiter = ClientRateLimiter(10)
        limiter.acquire("1.1.1.1")
        clock[0] += 61

        # WHEN another client sends a request
        limiter.acquire("2.2.2.2")

        # THEN only the bucket of the active client is kept
        assert set(limiter._buckets) == {"2.2.2.2"}  # pylint: disable=protected-access


class TestRateLimitMiddleware:
    def test_rejects_the_requests_above_the_limit(self):
        # GIVEN an app limited to 3 requests per minute
        client = TestClient(_build_app(3))

        # WHEN sending 4 requests
        responses = [client.get("/ping") for _ in range(4)]

        # THEN the first 3 are allowed
        assert [response.status_code for response in responses[:3]] == [HTTPStatus.OK] * 3

        # AND the 4th is rejected with a Retry-After header (1 token every 20 seconds)
        assert responses[3].status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert responses[3].json() == {"detail": "Too many requests, please try again later."}
        assert 1 <= int(responses[3].headers["Retry-After"]) <= 20

    def test_a_forged_forwarded_for_header_does_not_bypass_the_limit(self):
        # GIVEN an app limited to 2 requests per minute
        client = TestClient(_build_app(2))

        # WHEN sending requests that each claim to come from a different IP
        responses = [client.get("/ping", headers={"X-Forwarded-For": f"10.0.0.{index}"}) for index in range(3)]

        # THEN they are counted against the same client
        assert responses[2].status_code == HTTPStatus.TOO_MANY_REQUESTS


class TestAddRateLimiter:
    @staticmethod
    def _has_rate_limiter(app: FastAPI) -> bool:
        return any(middleware.cls is RateLimitMiddleware for middleware in app.user_middleware)

    def test_added_in_direct_mode(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN the direct ingress mode, with the default limit
        monkeypatch.setenv("INGRESS_MODE", "direct")
        monkeypatch.delenv("BACKEND_RATE_LIMIT_PER_MINUTE", raising=False)
        app = FastAPI()

        # WHEN adding the rate limiter
        add_rate_limiter(app)

        # THEN it is added
        assert self._has_rate_limiter(app)

    @pytest.mark.parametrize("given_ingress_mode", [None, "gateway"])
    def test_not_added_behind_the_gateway(self, monkeypatch: pytest.MonkeyPatch, given_ingress_mode):
        # GIVEN the gateway ingress mode (the default)
        if given_ingress_mode is None:
            monkeypatch.delenv("INGRESS_MODE", raising=False)
        else:
            monkeypatch.setenv("INGRESS_MODE", given_ingress_mode)
        app = FastAPI()

        # WHEN adding the rate limiter
        add_rate_limiter(app)

        # THEN it is not added, the gateway applies the rate limit
        assert not self._has_rate_limiter(app)

    def test_not_added_when_disabled(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN the direct ingress mode, with the rate limiter disabled
        monkeypatch.setenv("INGRESS_MODE", "direct")
        monkeypatch.setenv("BACKEND_RATE_LIMIT_PER_MINUTE", "0")
        app = FastAPI()

        # WHEN adding the rate limiter
        add_rate_limiter(app)

        # THEN it is not added
        assert not self._has_rate_limiter(app)
