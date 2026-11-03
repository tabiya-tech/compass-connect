"""
Response schema of the classifier /v2/classify endpoint.
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.agent.skill_linker.classifier.client.types import ClassifierSpan


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
