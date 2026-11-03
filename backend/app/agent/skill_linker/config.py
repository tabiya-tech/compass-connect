from enum import Enum


class SkillLinkerType(str, Enum):
    """
    The available implementations of the skill linker.
    Selected via the BACKEND_SKILL_LINKER environment variable.
    """

    LLM_PIPELINE = "llm_pipeline"
    """
    The original, LLM based linking and ranking pipeline (clustering, occupation inference, skill linking and ranking).
    """

    CLASSIFIER = "classifier"
    """
    The Tabiya classifier API, its version is selected via the CLASSIFIER_API_VERSION environment variable
    (see app.agent.skill_linker.classifier.ClassifierApiVersion).
    """
