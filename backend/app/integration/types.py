from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class HandoffAction(Enum):
    """
    Where the hand-off link lands the user.
    """
    CREATE = "create"
    """ The Compass home page. """
    SKILL_REPORT = "skill_report"
    """ The conversation that builds the skills report. """


class ExternalUserConflict(Enum):
    """
    Machine-readable reason of a 409 from the users endpoint (the `error_code` of the error body).
    """
    EXTERNAL_ID_BOUND_TO_OTHER_EMAIL = "external_id_bound_to_other_email"
    EMAIL_BOUND_TO_OTHER_EXTERNAL_ID = "email_bound_to_other_external_id"
    ACCOUNT_ALREADY_EXISTS = "account_already_exists"
    ACCOUNT_NOT_ELIGIBLE = "account_not_eligible"


class CreateExternalUserRequest(BaseModel):
    external_id: str = Field(min_length=1, max_length=128,
                             description="The calling platform's id for the user. Unique per Compass instance.")
    email: EmailStr = Field(description="The user's email; their Compass account.")
    action: HandoffAction = Field(default=HandoffAction.SKILL_REPORT,
                                  description="Where the hand-off link lands the user. create: the Compass home "
                                              "page. skill_report: the conversation that builds the skills report.")

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.lower()

    class Config:
        extra = "forbid"
        str_strip_whitespace = True


class ExternalUserResponse(BaseModel):
    external_id: str
    email: str
    created_at: datetime


class HandoffLinkResponse(BaseModel):
    url: str
    expires_at: datetime


class CreateExternalUserResponse(BaseModel):
    result: str = Field(description="What happened, in a short human-readable sentence.")
    user: ExternalUserResponse
    link: HandoffLinkResponse = Field(description="The hand-off link that logs the user in.")


class HandoffLink(BaseModel):
    """
    The live hand-off link of a user, as stored. Only the hash of the token is kept.
    """
    token_hash: str
    action: HandoffAction
    expires_at: datetime


class ExternalUser(BaseModel):
    """
    A user created by another platform through the integration API, as stored.
    """
    external_id: str
    email: str
    user_id: Optional[str] = None
    """
    The Firebase user id. Empty until the Firebase account is created, so a retry after a half-finished request
    finishes it instead of mistaking it for an account created by other means.
    """
    link: Optional[HandoffLink] = None
    """
    The only link that works for this user. Issuing a new one replaces it.
    """
    created_at: datetime
    updated_at: datetime


class HandoffExchangeRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)

    class Config:
        extra = "forbid"


class HandoffExchangeResponse(BaseModel):
    custom_token: str = Field(description="A Firebase custom token, for signInWithCustomToken.")
    action: HandoffAction = Field(description="Where the user lands.")
