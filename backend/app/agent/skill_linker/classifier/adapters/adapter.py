from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field

from app.agent.skill_linker.classifier.client import ClassifierEntityType
from app.agent.skill_linker.classifier.skill_ranking import SkillCandidate

EXTRACT_ENTITIES: list[ClassifierEntityType] = ["skill", "occupation"]
"""
The entities the classifier is asked to extract from the experience.
"""


class OccupationMatch(BaseModel):
    """
    A taxonomy occupation matched by the classifier for an extracted occupation entity.
    """

    label: str
    esco_code: Optional[str] = None
    score: float = 0.0


class ClassifierMatches(BaseModel):
    """
    The result of classifying an experience, independent of the classifier API version.
    """

    skill_candidates: list[SkillCandidate] = Field(default_factory=list)

    title_candidates: list[str] = Field(default_factory=list)
    """
    The labels of the best occupation match of each extracted occupation, by score descending, deduplicated.
    """

    occupation_matches: list[OccupationMatch] = Field(default_factory=list)
    """
    The best occupation match of each extracted occupation, by score descending, deduplicated.
    """


class IClassifierAdapter(ABC):
    """
    Calls one version of the classifier API and adapts its response to taxonomy skill candidates.
    """

    @abstractmethod
    async def classify(self, *,
                       experience_title: str,
                       responsibilities: list[str],
                       overview: Optional[str] = None) -> ClassifierMatches:
        """
        :raises ClassifierServiceError: if the classifier request fails
        """
        raise NotImplementedError()


def to_description(responsibilities: list[str], overview: Optional[str] = None) -> str:
    responsibilities_text = "\n".join(f"- {responsibility}" for responsibility in responsibilities)
    cleaned_overview = (overview or "").strip()
    if not cleaned_overview:
        return responsibilities_text
    if not responsibilities_text:
        return cleaned_overview
    return f"{cleaned_overview}\n\nResponsibilities:\n{responsibilities_text}"


def to_title_candidates(occupation_matches: list[tuple[float, str]]) -> list[str]:
    """
    :param occupation_matches: (score, label) of the best match of each extracted occupation
    """
    labels = [label for _, label in sorted(occupation_matches, key=lambda m: m[0], reverse=True)]
    return list(dict.fromkeys(labels))


def to_occupation_matches(matches: list[OccupationMatch]) -> list[OccupationMatch]:
    """
    Sort occupation matches by score descending and deduplicate by ESCO code (when present) or normalized label.
    """
    sorted_matches = sorted(matches, key=lambda m: m.score, reverse=True)
    seen: set[str] = set()
    unique: list[OccupationMatch] = []
    for match in sorted_matches:
        key = match.esco_code.strip() if match.esco_code and match.esco_code.strip() else match.label.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(match)
    return unique
