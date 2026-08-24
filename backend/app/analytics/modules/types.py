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
