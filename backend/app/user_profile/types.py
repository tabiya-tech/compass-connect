"""
Types for the User Profile module.

Provides cross-module user profile data models that aggregate information
from Skills & Interests (experiences, skills) and registration (personal data).
"""

from typing import Optional, Union

from pydantic import BaseModel, Field


class ExperienceSummary(BaseModel):
    """
    Simplified summary of a user's explored experience with discovered skills.
    """

    title: str = Field(description="Experience title as the user described it")
    normalized_title: Optional[str] = Field(default=None, description="Taxonomy-normalised occupation title (e.g. 'Pastry Chef')")
    company: Optional[str] = Field(default=None, description="Company or organization name")
    work_type: Optional[str] = Field(default=None, description="Type of work (e.g. paid_work, volunteer)")
    skills: list[str] = Field(default_factory=list, description="Skill preferred labels (top skills)")

    class Config:
        """Pydantic configuration."""
        extra = "forbid"


class UserProfileData(BaseModel):
    """
    Aggregated user profile data from across modules.

    Combines explored experiences and skills from Skills & Interests
    with personal data from registration (programme, school, year).
    """

    experiences: list[ExperienceSummary] = Field(
        default_factory=list,
        description="Simplified summaries of explored experiences with skills",
    )
    personal_data: dict[str, Union[str, list[str]]] = Field(
        default_factory=dict,
        description="Personal data from registration (e.g. programme, school, year)",
    )

    class Config:
        """Pydantic configuration."""
        extra = "forbid"
