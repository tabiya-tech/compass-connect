import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.agent.skill_linker.classifier.client.response_v1 import ClassifierV1Response
from app.agent.skill_linker.classifier.client.response_v2 import ClassifierV2Response
from app.agent.skill_linker.classifier.client.types import ClassifierApiVersion, \
    ClassifierEntityType

Response_ = TypeVar("Response_", bound=BaseModel)


class ClassifierServiceError(Exception):
    """Raised when a classifier request fails (HTTP, transport, or response shape)."""


class ClassifierClient:
    """
    Transport-only client for the Tabiya classifier API (https://<host>/openapi.json).
    Authentication is via `x-api-key`.
    """

    def __init__(self, *, base_url: str, api_key: str, timeout: float = 60.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._logger = logging.getLogger(self.__class__.__name__)

    async def classify_v1(self, *,
                          title: str,
                          description: str,
                          extract_entities: list[ClassifierEntityType],
                          top_k: int,
                          min_similarity: float) -> ClassifierV1Response:
        return await self._classify(ClassifierV1Response, ClassifierApiVersion.V1,
                                    title=title, description=description, extract_entities=extract_entities,
                                    top_k=top_k, min_similarity=min_similarity)

    async def classify_v2(self, *,
                          title: str,
                          description: str,
                          extract_entities: list[ClassifierEntityType],
                          top_k: int,
                          min_similarity: float) -> ClassifierV2Response:
        return await self._classify(ClassifierV2Response, ClassifierApiVersion.V2,
                                    title=title, description=description, extract_entities=extract_entities,
                                    top_k=top_k, min_similarity=min_similarity)

    async def _classify(self, response_cls: type[Response_], version: ClassifierApiVersion, *,
                        title: str,
                        description: str,
                        extract_entities: list[ClassifierEntityType],
                        top_k: int,
                        min_similarity: float) -> Response_:
        url = f"{self._base_url}/{version.value}/classify"
        payload = {
            "title": title,
            "description": description,
            "options": {
                "extract_entities": extract_entities,
                "top_k": top_k,
                "min_similarity": min_similarity,
            },
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={"x-api-key": self._api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=self._timeout
                )
                response.raise_for_status()
                return response_cls.model_validate(response.json())
        except httpx.HTTPStatusError as e:
            raise ClassifierServiceError(
                f"Classifier returned HTTP {e.response.status_code} on {url}: {e.response.text}") from e
        except httpx.RequestError as e:
            raise ClassifierServiceError(f"Failed to connect to the classifier on {url}: {e}") from e
        except ValidationError as e:
            raise ClassifierServiceError(
                f"Classifier response from {url} does not match {response_cls.__name__}: {e}") from e
