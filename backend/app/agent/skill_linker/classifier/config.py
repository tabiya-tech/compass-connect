from pydantic import BaseModel, ConfigDict, Field


class ClassifierSkillLinkerConfig(BaseModel):
    number_of_top_skills: int = Field(default=5, gt=0)
    """
    The number of skills returned as the top skills of the experience.
    """

    top_k_per_entity: int = Field(default=3, ge=1, le=50)
    """
    The number of taxonomy matches the classifier returns for each extracted entity.
    The best match of each entity is a top skill candidate, the others end up in the remaining skills.
    """

    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    """
    Matches with a similarity score lower than this are dropped by the classifier.
    """

    max_rerank_candidates: int = Field(default=30, ge=1, le=200)
    """
    The number of best scoring candidates sent to the LLM reranker, when one is configured.
    """

    model_config = ConfigDict(extra="forbid")
