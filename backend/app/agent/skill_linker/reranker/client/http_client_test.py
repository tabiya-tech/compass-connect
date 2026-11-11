import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.agent.skill_linker.reranker.client import GoogleIdTokenProvider, IdTokenError, LlmRerankerClient, \
    LlmRerankerServiceError, RerankCandidate

_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patch_transport(handler):
    """Route the requests of the client through the given handler instead of the network."""
    return patch("app.agent.skill_linker.reranker.client.http_client.httpx.AsyncClient",
                 side_effect=lambda *args, **kwargs: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler)))


def _given_token_provider(**kwargs) -> GoogleIdTokenProvider:
    token_provider = MagicMock(spec=GoogleIdTokenProvider)
    token_provider.get_token = AsyncMock(**kwargs) if kwargs else AsyncMock(return_value="test-id-token")
    return token_provider


async def _rank_skills(client: LlmRerankerClient):
    return await client.rank_skills(title="Baker", company="Bakery", work_type="Unpaid other",
                                    responsibilities=["I bake bread"],
                                    candidates=[RerankCandidate(id="a", label="bake goods", description="Bake.",
                                                                score=0.9)],
                                    max_skills=5)


class TestRankSkills:
    @pytest.mark.asyncio
    async def test_sends_request(self):
        # GIVEN a reranker that ranks one skill
        actual_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            actual_requests.append(request)
            return httpx.Response(200, json={"ranked_ids": ["a"], "discarded_ids": [], "timings": {"llm_s": 1.0},
                                             "model": "m"})

        given_client = LlmRerankerClient(base_url="https://reranker.test/", token_provider=_given_token_provider())

        # WHEN rank_skills is called
        with _patch_transport(handler):
            actual_response = await _rank_skills(given_client)

        # THEN the request is sent to the skills endpoint, with the ID token
        assert len(actual_requests) == 1
        actual_request = actual_requests[0]
        assert str(actual_request.url) == "https://reranker.test/rank/skills"
        assert actual_request.headers["Authorization"] == "Bearer test-id-token"
        # AND the body contains the experience and the candidates
        assert json.loads(actual_request.content) == {
            "experience": {"title": "Baker", "company": "Bakery", "work_type": "Unpaid other",
                           "responsibilities": ["I bake bread"]},
            "candidates": [{"id": "a", "label": "bake goods", "description": "Bake.", "score": 0.9}],
            "max_skills": 5,
        }
        # AND the response is parsed
        assert actual_response.ranked_ids == ["a"]
        assert actual_response.model == "m"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("handler", [
        lambda request: httpx.Response(403, text="Forbidden"),
        lambda request: httpx.Response(500, json={"detail": "LLM invocation error: LlmInvocationError"}),
        lambda request: httpx.Response(200, json={"unexpected": True}),
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("unreachable")),
    ], ids=["forbidden", "server error", "malformed body", "connect error"])
    async def test_raises_on_failure(self, handler):
        # GIVEN a reranker that fails
        given_client = LlmRerankerClient(base_url="https://reranker.test", token_provider=_given_token_provider())

        # WHEN rank_skills is called
        # THEN an LlmRerankerServiceError is raised
        with _patch_transport(handler):
            with pytest.raises(LlmRerankerServiceError):
                await _rank_skills(given_client)

    @pytest.mark.asyncio
    async def test_raises_when_the_id_token_cannot_be_fetched(self):
        # GIVEN an ID token provider that fails
        given_client = LlmRerankerClient(base_url="https://reranker.test",
                                         token_provider=_given_token_provider(side_effect=IdTokenError("no creds")))

        # WHEN rank_skills is called
        # THEN an LlmRerankerServiceError is raised, without calling the reranker
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("the reranker must not be called without a token")

        with _patch_transport(handler):
            with pytest.raises(LlmRerankerServiceError):
                await _rank_skills(given_client)
