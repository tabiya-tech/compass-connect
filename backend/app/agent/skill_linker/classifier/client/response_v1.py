"""
Response schema of the classifier /v1/classify endpoint.
"""
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.agent.skill_linker.classifier.client.types import ClassifierSpan


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
