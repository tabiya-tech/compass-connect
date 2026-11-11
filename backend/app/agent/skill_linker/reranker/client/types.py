from typing import Optional

from pydantic import BaseModel


class RerankCandidate(BaseModel):
    """
    A candidate skill. The id is returned in the ranked ids, the label and description are shown to the LLM.
    """

    id: str
    label: str
    description: str = ""
    score: Optional[float] = None
