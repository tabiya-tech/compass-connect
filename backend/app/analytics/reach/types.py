from pydantic import BaseModel


class ReachSummary(BaseModel):
    """
    Headline reach numbers for the selected scope and date range.

    Mirrors the ReachResponse.summary contract consumed by the compass-analytics
    dashboard, so this endpoint can be mapped 1:1 by that backend's repository.
    """
    total_users: int
    active_users_30d: int
    total_logins: int
    avg_logins_per_user: float
    avg_session_minutes: int


class TimeSeriesPoint(BaseModel):
    """
    One time bucket of the reach series (currently one point per day).
    """
    label: str
    cumulative: int
    added: int
    new_users: int
    returning: int
    logins: int


class ReachResponse(BaseModel):
    summary: ReachSummary
    series: list[TimeSeriesPoint]
