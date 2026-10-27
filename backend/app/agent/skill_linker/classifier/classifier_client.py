import logging
from typing import Any, Literal, Optional, TypeVar

import httpx
from pydantic import BaseModel, Field, ValidationError

ClassifierApiVersion = Literal["v1", "v2"]
ClassifierEntityType = Literal["occupation", "skill", "qualification"]

Response_ = TypeVar("Response_", bound=BaseModel)


class ClassifierServiceError(Exception):
    """Raised when a classifier request fails (HTTP, transport, or response shape)."""


class ClassifierSpan(BaseModel):
    start: int
    end: int


# ---------------------------------------------------------------------------
# /v1/classify
# ---------------------------------------------------------------------------

class ClassifierV1Entity(BaseModel):
    entity_type: str
    surface_form: str
    span: ClassifierSpan
    linked_entities: Optional[list[dict[str, Any]]] = None
    """
    ESCO matches ordered by similarity score descending. The shape of the matches is not part of the API contract,
    they usually carry a `label` and a `similarity_score`.
    """


class ClassifierV1Classification(BaseModel):
    entities: list[ClassifierV1Entity]
    entity_counts: dict[str, int] = Field(default_factory=dict)


class ClassifierV1Response(BaseModel):
    classification: ClassifierV1Classification
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# /v2/classify
# ---------------------------------------------------------------------------

class ClassifierV2TaxonomyEntity(BaseModel):
    """
    The taxonomy entity of a match. Skills, occupations and qualifications share these fields,
    the type specific fields are optional.
    """
    uuid: str
    origin_uuid: str = ""
    uuid_history: list[str] = Field(default_factory=list)
    preferred_label: str
    origin_uri: str = ""
    alt_labels: list[str] = Field(default_factory=list)
    description: str = ""
    skill_type: Optional[str] = None
    esco_code: Optional[str] = None


class ClassifierV2Match(BaseModel):
    entity_type: str
    similarity_score: float
    entity: ClassifierV2TaxonomyEntity


class ClassifierV2Entity(BaseModel):
    entity_type: str
    surface_form: str
    span: ClassifierSpan
    matches: list[ClassifierV2Match] = Field(default_factory=list)


class ClassifierV2Metadata(BaseModel):
    classifier_version: str = ""
    ner_model: str = ""
    nel_model_id: str = ""
    taxonomy_model_id: str = ""
    processing_time_ms: float = 0.0


class ClassifierV2Response(BaseModel):
    entities: list[ClassifierV2Entity]
    metadata: ClassifierV2Metadata = Field(default_factory=ClassifierV2Metadata)


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
        return await self._classify(ClassifierV1Response, "v1",
                                    title=title, description=description, extract_entities=extract_entities,
                                    top_k=top_k, min_similarity=min_similarity)

    async def classify_v2(self, *,
                          title: str,
                          description: str,
                          extract_entities: list[ClassifierEntityType],
                          top_k: int,
                          min_similarity: float) -> ClassifierV2Response:
        return await self._classify(ClassifierV2Response, "v2",
                                    title=title, description=description, extract_entities=extract_entities,
                                    top_k=top_k, min_similarity=min_similarity)

    async def _classify(self, response_cls: type[Response_], version: ClassifierApiVersion, *,
                        title: str,
                        description: str,
                        extract_entities: list[ClassifierEntityType],
                        top_k: int,
                        min_similarity: float) -> Response_:
        url = f"{self._base_url}/{version}/classify"
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
