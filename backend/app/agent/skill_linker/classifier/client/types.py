from enum import Enum
from typing import Literal

from pydantic import BaseModel


class ClassifierApiVersion(str, Enum):
    """
    The version of the Tabiya classifier API, the path segment of its classify endpoint (/<version>/classify).
    Selected via the CLASSIFIER_API_VERSION environment variable.
    """

    V1 = "v1"
    """
    The /v1/classify endpoint.
    """

    V2 = "v2"
    """
    The /v2/classify endpoint.
    """


ClassifierEntityType = Literal["occupation", "skill", "qualification"]


class ClassifierSpan(BaseModel):
    start: int
    end: int
