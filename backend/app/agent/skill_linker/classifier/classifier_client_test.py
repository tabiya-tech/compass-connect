import json
from unittest.mock import patch

import httpx
import pytest

from app.agent.skill_linker.classifier.classifier_client import ClassifierClient, ClassifierServiceError

_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patch_transport(handler):
    """Route the requests of the client through the given handler instead of the network."""
    return patch("app.agent.skill_linker.classifier.classifier_client.httpx.AsyncClient",
                 side_effect=lambda *args, **kwargs: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler)))


@pytest.fixture
def given_client() -> ClassifierClient:
    return ClassifierClient(base_url="https://classifier.test/", api_key="test-api-key")


class TestClassify:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("version", ["v1", "v2"])
    async def test_sends_request(self, given_client: ClassifierClient, version: str):
        # GIVEN a classifier that returns a valid empty response
        actual_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            actual_requests.append(request)
            if version == "v1":
                return httpx.Response(200, json={"classification": {"entities": [], "entity_counts": {}}, "metadata": {}})
            return httpx.Response(200, json={"entities": [], "metadata": {}})

        # WHEN classify is called
        with _patch_transport(handler):
            classify = given_client.classify_v1 if version == "v1" else given_client.classify_v2
            await classify(title="Baker", description="- bake bread", extract_entities=["skill"], top_k=3,
                           min_similarity=0.5)

        # THEN the request is sent to the versioned endpoint, with the api key
        assert len(actual_requests) == 1
        actual_request = actual_requests[0]
        assert str(actual_request.url) == f"https://classifier.test/{version}/classify"
        assert actual_request.headers["x-api-key"] == "test-api-key"
        # AND the body contains the text and the options
        assert json.loads(actual_request.content) == {
            "title": "Baker",
            "description": "- bake bread",
            "options": {"extract_entities": ["skill"], "top_k": 3, "min_similarity": 0.5},
        }

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self, given_client: ClassifierClient):
        # GIVEN a classifier that responds with an error
        # WHEN classify is called
        # THEN a ClassifierServiceError is raised
        with _patch_transport(lambda request: httpx.Response(401, json={"message": "UNAUTHENTICATED"})):
            with pytest.raises(ClassifierServiceError):
                await given_client.classify_v2(title="Baker", description="", extract_entities=["skill"], top_k=3,
                                               min_similarity=0.0)

    @pytest.mark.asyncio
    async def test_raises_on_unexpected_response(self, given_client: ClassifierClient):
        # GIVEN a classifier that responds with an unexpected shape
        # WHEN classify is called
        # THEN a ClassifierServiceError is raised
        with _patch_transport(lambda request: httpx.Response(200, json={"foo": "bar"})):
            with pytest.raises(ClassifierServiceError):
                await given_client.classify_v2(title="Baker", description="", extract_entities=["skill"], top_k=3,
                                               min_similarity=0.0)

    @pytest.mark.asyncio
    async def test_raises_on_transport_error(self, given_client: ClassifierClient):
        # GIVEN a classifier that cannot be reached
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unreachable", request=request)

        # WHEN classify is called
        # THEN a ClassifierServiceError is raised
        with _patch_transport(handler):
            with pytest.raises(ClassifierServiceError):
                await given_client.classify_v1(title="Baker", description="", extract_entities=["skill"], top_k=3,
                                               min_similarity=0.0)
