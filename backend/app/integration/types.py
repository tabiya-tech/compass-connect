import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator, model_validator

EXTERNAL_ID_PATTERN = r"^[A-Za-z0-9._:@-]{1,128}$"
"""
The ids a platform can use. No `/`, so an id can be a path segment (Starlette decodes `%2F` before routing), and no
free text, which leaves less room for personal data in the id.
"""

WEBHOOK_SECRET_PATTERN = r"[A-Za-z0-9_-]{43}"  # nosec B105 # a format, not a credential
"""
32 random bytes, base64url without padding (the JWK `k` format), e.g. Python `secrets.token_urlsafe(32)` or Node
`crypto.randomBytes(32).toString("base64url")`. It is the AES-256 key of the webhook notifications.
"""


class HandoffAction(Enum):
    """
    Where the hand-off link lands the user.
    """
    CREATE = "create"
    """ The Compass home page. """
    BUILD_PROFILE = "build_profile"
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
    external_id: str = Field(pattern=EXTERNAL_ID_PATTERN,
                             description="The calling platform's id for the user. Unique per Compass instance. "
                                         "1 to 128 characters: letters, digits and . _ : @ -")
    email: EmailStr = Field(description="The user's email; their Compass account.")
    action: HandoffAction = Field(default=HandoffAction.BUILD_PROFILE,
                                  description="Where the hand-off link lands the user. create: the Compass home "
                                              "page. build_profile: the conversation that builds the skills report.")
    return_url: Optional[str] = Field(default=None, max_length=2048,
                                      description="Where the user goes back to when they are done. Its origin must "
                                                  "be allowed on the instance. Each call replaces it; a call "
                                                  "without it removes it.")
    webhook_url: Optional[str] = Field(default=None, max_length=2048,
                                       description="Where Compass notifies the platform about the user, e.g. when "
                                                   "they finish their conversation. Its origin must be allowed on "
                                                   "the instance, and webhooks enabled. Needs webhook_secret. Each "
                                                   "call replaces it; a call without it removes it.")
    webhook_secret: Optional[SecretStr] = Field(default=None,
                                                description="The key that encrypts and authenticates the "
                                                            "notifications: 32 random bytes, base64url without "
                                                            "padding (43 characters). Chosen by the platform, never "
                                                            "returned. Required with webhook_url.")

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("external_id")
    @classmethod
    def _not_a_dot_segment(cls, value: str) -> str:
        # `.` and `..` match the pattern, but clients resolve them in a URL path: `/users/../results` never reaches
        # the results route. Not in the pattern: lookarounds are not supported by pydantic's regex engine.
        if value in (".", ".."):
            raise ValueError("external_id cannot be '.' or '..'")
        return value

    @field_validator("webhook_secret")
    @classmethod
    def _secret_is_32_bytes(cls, value: Optional[SecretStr]) -> Optional[SecretStr]:
        if value is not None and not re.fullmatch(WEBHOOK_SECRET_PATTERN, value.get_secret_value()):
            raise ValueError("webhook_secret must be 32 random bytes, base64url without padding (43 characters)")
        return value

    @model_validator(mode="after")
    def _webhook_url_and_secret_together(self) -> "CreateExternalUserRequest":
        if (self.webhook_url is None) != (self.webhook_secret is None):
            raise ValueError("webhook_url and webhook_secret must be sent together")
        return self

    class Config:
        extra = "forbid"
        str_strip_whitespace = True


class ExternalUserResponse(BaseModel):
    external_id: str
    email: str
    return_url: Optional[str] = Field(default=None, description="The return URL stored by this call.")
    webhook_url: Optional[str] = Field(default=None, description="The webhook URL stored by this call. The secret "
                                                                 "is never returned.")
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


class Webhook(BaseModel):
    """
    Where and how to notify the platform about a user, as stored. URL and secret are always set and replaced together.
    """
    url: str
    secret: SecretStr


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
    webhook: Optional[Webhook] = None
    """
    Empty: the platform is not notified about this user.
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

