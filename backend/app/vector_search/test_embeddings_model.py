from unittest.mock import patch

import pytest
import vertexai
from google.cloud.aiplatform import initializer as aiplatform_initializer

from app.vector_search.embeddings_model import GoogleEmbeddingService

GEN_AI_LOCATION = "global"
EMBEDDINGS_REGION = "us-central1"


class _FakeEmbedding:
    def __init__(self, values: list[float]):
        self.values = values


class _FakeEndpoint:
    """Records the Vertex AI location that is set when the prediction client is created."""

    def __init__(self):
        self.client_location: str | None = None

    @property
    def _prediction_async_client(self):
        self.client_location = aiplatform_initializer.global_config.location
        return object()


class _FakeTextEmbeddingModel:
    def __init__(self, location: str):
        self.location = location
        self._endpoint = _FakeEndpoint()

    async def get_embeddings_async(self, inputs):
        return [_FakeEmbedding([0.1, 0.2]) for _ in inputs]


def _fake_from_pretrained(_model_name: str) -> _FakeTextEmbeddingModel:
    return _FakeTextEmbeddingModel(location=aiplatform_initializer.global_config.location)


@pytest.fixture
def given_gen_ai_location(monkeypatch):
    """Initializes the Vertex AI SDK with the gen-AI location, as BasicLLM does, and restores the previous location."""
    monkeypatch.setenv("VERTEX_API_EMBEDDINGS_REGION", EMBEDDINGS_REGION)
    previous_location = aiplatform_initializer.global_config.location
    vertexai.init(location=GEN_AI_LOCATION)
    yield GEN_AI_LOCATION
    vertexai.init(location=previous_location)


class TestGoogleEmbeddingService:
    def test_constructing_uses_the_embeddings_region_and_restores_the_gen_ai_location(self, given_gen_ai_location: str):
        # GIVEN the Vertex AI SDK is initialized with the gen-AI location and the embeddings region differs from it

        # WHEN the embedding service is constructed
        with patch("app.vector_search.embeddings_model.TextEmbeddingModel.from_pretrained",
                   side_effect=_fake_from_pretrained):
            service = GoogleEmbeddingService(model_name="foo-embedding-model")

        # THEN expect the model to be resolved in the embeddings region
        assert service.model.location == EMBEDDINGS_REGION
        # AND its prediction client to be created in the embeddings region
        assert service.model._endpoint.client_location == EMBEDDINGS_REGION
        # AND the gen-AI location to be restored, so that Gemini models created later do not use the embeddings region
        assert aiplatform_initializer.global_config.location == given_gen_ai_location

    @pytest.mark.asyncio
    async def test_embedding_does_not_change_the_gen_ai_location(self, given_gen_ai_location: str):
        # GIVEN an embedding service constructed while the Vertex AI SDK is initialized with the gen-AI location
        with patch("app.vector_search.embeddings_model.TextEmbeddingModel.from_pretrained",
                   side_effect=_fake_from_pretrained):
            service = GoogleEmbeddingService(model_name="foo-embedding-model")

        # WHEN a text is embedded
        actual_embedding = await service.embed("foo")

        # THEN expect the embedding to be returned
        assert actual_embedding == [0.1, 0.2]
        # AND the gen-AI location to be unchanged
        assert aiplatform_initializer.global_config.location == given_gen_ai_location

    def test_constructing_restores_the_gen_ai_location_when_loading_the_model_fails(self, given_gen_ai_location: str):
        # GIVEN loading the embedding model fails
        given_error = RuntimeError("foo")

        # WHEN the embedding service is constructed
        # THEN expect the error to be raised
        with patch("app.vector_search.embeddings_model.TextEmbeddingModel.from_pretrained", side_effect=given_error), \
                pytest.raises(RuntimeError) as error_info:
            GoogleEmbeddingService(model_name="foo-embedding-model")
        assert error_info.value is given_error
        # AND the gen-AI location to be restored
        assert aiplatform_initializer.global_config.location == given_gen_ai_location
