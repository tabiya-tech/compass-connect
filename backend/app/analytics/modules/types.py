from pydantic import BaseModel


class BuildYourProfileSummary(BaseModel):
    started_users: int
    started_percentage: float
    completed_users: int
    avg_completion_minutes: float


class BuildYourProfileSeriesPoint(BaseModel):
    label: str
    started: int
    completed: int
    skills_reports_generated: int
    skills_reports_downloaded: int


class ConversationPhaseReach(BaseModel):
    """One funnel stage: how many distinct users reached at least this far in the conversation."""

    id: str
    reached: int


class BuildYourProfileResponse(BaseModel):
    summary: BuildYourProfileSummary
    series: list[BuildYourProfileSeriesPoint]
    phases: list[ConversationPhaseReach]


class SubModuleProgress(BaseModel):
    id: str
    name: str
    started: int
    completed: int

    class Config:
        extra = "forbid"


class JobReadinessResponse(BaseModel):
    """
    Job Readiness (career readiness) analytics for the selected scope.

    started_percentage: share of registered users who started at least one sub-module.
    sub_modules: per-module started/completed counts, in sort_order from the module registry.
    degraded: always False from the real endpoint; reserved for the caller's degraded-upstream flag.
    """

    started_percentage: float
    sub_modules: list[SubModuleProgress]
    degraded: bool = False

    class Config:
        extra = "forbid"


class JobsSummary(BaseModel):
    jobs_sourced: int


class JobsResponse(BaseModel):
    summary: JobsSummary
