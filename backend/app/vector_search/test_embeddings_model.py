from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.vector_search.embeddings_model import GoogleEmbeddingService


def _fake_client() -> MagicMock:
    """A fake google-genai client that returns an embedding [index, index] for each text, in order."""
    client = MagicMock()

    async def _embed_content(*, model, contents, config):  # pylint: disable=unused-argument
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[float(len(text)), 1.0]) for text in contents])

    client.aio.models.embed_content = AsyncMock(side_effect=_embed_content)
    return client


class TestGoogleEmbeddingService:
    def test_creates_the_client_for_the_embeddings_region(self, monkeypatch):
        # GIVEN the embeddings region
        given_region = "us-central1"
        monkeypatch.setenv("VERTEX_API_EMBEDDINGS_REGION", given_region)

        # WHEN the embedding service is constructed
        with patch("app.vector_search.embeddings_model.genai.Client") as mock_client_class:
            GoogleEmbeddingService(model_name="foo-model")

        # THEN expect a Vertex AI client for the embeddings region
        mock_client_class.assert_called_once_with(vertexai=True, location=given_region)

    def test_raises_when_the_embeddings_region_is_not_set(self, monkeypatch):
        # GIVEN the embeddings region is not set
        monkeypatch.delenv("VERTEX_API_EMBEDDINGS_REGION", raising=False)

        # WHEN the embedding service is constructed
        # THEN expect a ValueError
        with pytest.raises(ValueError):
            GoogleEmbeddingService(model_name="foo-model")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_region, expected_batch_size", [
        ("us-central1", 250),
        ("europe-west4", 5),
    ])
    async def test_embeds_the_texts_in_batches_of_the_region(self, monkeypatch, given_region: str, expected_batch_size: int):
        # GIVEN the embeddings region
        monkeypatch.setenv("VERTEX_API_EMBEDDINGS_REGION", given_region)
        # AND more texts than fit in a batch
        given_texts = ["a" * (i + 1) for i in range(expected_batch_size + 1)]
        # AND an embedding service with a fake client
        given_client = _fake_client()
        with patch("app.vector_search.embeddings_model.genai.Client", return_value=given_client):
            given_service = GoogleEmbeddingService(model_name="foo-model")

        # WHEN the texts are embedded
        actual_embeddings = await given_service.embed_batch(given_texts)

        # THEN expect an embedding for each text, in order
        assert actual_embeddings == [[float(len(text)), 1.0] for text in given_texts]
        # AND the texts to be sent in two batches of at most the region's batch size
        actual_batches = [call.kwargs["contents"] for call in given_client.aio.models.embed_content.call_args_list]
        assert [len(batch) for batch in actual_batches] == [expected_batch_size, 1]
        # AND the model and the retrieval query task type to be used
        actual_call = given_client.aio.models.embed_content.call_args_list[0]
        assert actual_call.kwargs["model"] == "foo-model"
        assert actual_call.kwargs["config"].task_type == "RETRIEVAL_QUERY"

    @pytest.mark.asyncio
    async def test_rejects_empty_texts(self, monkeypatch):
        # GIVEN an embedding service
        monkeypatch.setenv("VERTEX_API_EMBEDDINGS_REGION", "us-central1")
        with patch("app.vector_search.embeddings_model.genai.Client", return_value=_fake_client()):
            given_service = GoogleEmbeddingService(model_name="foo-model")

        # WHEN an empty text is embedded
        # THEN expect a ValueError
        with pytest.raises(ValueError):
            await given_service.embed_batch(["foo", "  "])
