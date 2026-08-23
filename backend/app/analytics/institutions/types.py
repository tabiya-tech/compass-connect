from typing import Optional

from pydantic import BaseModel


class InstitutionSummary(BaseModel):
    """
    Per-institution summary returned by the server-to-server analytics endpoint.

    Mirrors the InstitutionsResponse contract consumed by the compass-analytics
    dashboard. Fields are limited to what Compass actually tracks — login counts
    and session duration are not available.
    """

    institution_id: str
    institution_name: str
    registered_users: int
    active_users_7d: int
    skills_discovery_started_pct: Optional[float] = None
    skills_discovery_completed_pct: Optional[float] = None
    career_readiness_started_pct: Optional[float] = None
    career_readiness_completed_pct: Optional[float] = None
    career_explorer_started_pct: Optional[float] = None


class InstitutionsResponse(BaseModel):
    institutions: list[InstitutionSummary]
