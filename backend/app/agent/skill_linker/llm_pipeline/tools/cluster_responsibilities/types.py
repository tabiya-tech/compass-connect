from pydantic import BaseModel, Field

from app.agent.agent_types import LLMStats


class Cluster(BaseModel):
    cluster_name: str = Field(description="The name for the cluster, representative of the responsibilities it contains.")
    responsibilities: list[str] = Field(description="The responsibilities of the cluster, at least one.")

    class Config:
        extra = "forbid"


class ClusterResponsibilitiesResponse(BaseModel):
    clusters: list[Cluster]
    llm_stats: list[LLMStats]

    class Config:
        extra = "forbid"
