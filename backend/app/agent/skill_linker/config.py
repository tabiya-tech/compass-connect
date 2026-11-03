from enum import Enum


class SkillLinkerType(str, Enum):
    """
    The available implementations of the skill linker.
    Selected via the BACKEND_SKILL_LINKER environment variable.
    """

    LINKING_AND_RANKING_PIPELINE = "linking_and_ranking_pipeline"
    """
    The original, LLM based linking and ranking pipeline (clustering, occupation inference, skill linking and ranking).
    """

    CLASSIFIER_V1 = "classifier_v1"
    """
    The Tabiya classifier API, using the /v1/classify endpoint.
    """

    CLASSIFIER_V2 = "classifier_v2"
    """
    The Tabiya classifier API, using the /v2/classify endpoint.
    """

    @property
    def is_classifier(self) -> bool:
        return self in (SkillLinkerType.CLASSIFIER_V1, SkillLinkerType.CLASSIFIER_V2)
