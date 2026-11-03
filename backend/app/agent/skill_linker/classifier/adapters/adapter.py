from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from app.agent.skill_linker.classifier.client import ClassifierEntityType
from app.agent.skill_linker.classifier.skill_ranking import SkillCandidate

EXTRACT_ENTITIES: list[ClassifierEntityType] = ["skill", "occupation"]
"""
The entities the classifier is asked to extract from the experience.
"""


class ClassifierMatches(BaseModel):
    """
    The result of classifying an experience, independent of the classifier API version.
    """

    skill_candidates: list[SkillCandidate] = Field(default_factory=list)

    title_candidates: list[str] = Field(default_factory=list)
    """
    The labels of the best occupation match of each extracted occupation, by score descending, deduplicated.
    """


class IClassifierAdapter(ABC):
    """
    Calls one version of the classifier API and adapts its response to taxonomy skill candidates.
    """

    @abstractmethod
    async def classify(self, *, experience_title: str, responsibilities: list[str]) -> ClassifierMatches:
        """
        :raises ClassifierServiceError: if the classifier request fails
        """
        raise NotImplementedError()


def to_description(responsibilities: list[str]) -> str:
    return "\n".join(f"- {responsibility}" for responsibility in responsibilities)


def to_title_candidates(occupation_matches: list[tuple[float, str]]) -> list[str]:
    """
    :param occupation_matches: (score, label) of the best match of each extracted occupation
    """
    labels = [label for _, label in sorted(occupation_matches, key=lambda m: m[0], reverse=True)]
    return list(dict.fromkeys(labels))
