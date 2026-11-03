from typing import Literal

from pydantic import BaseModel

ClassifierApiVersion = Literal["v1", "v2"]
ClassifierEntityType = Literal["occupation", "skill", "qualification"]


class ClassifierSpan(BaseModel):
    start: int
    end: int
