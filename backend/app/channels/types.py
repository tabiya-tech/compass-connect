from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.conversations.constants import MAX_MESSAGE_LENGTH

CHANNEL_USER_ID_PATTERN = r"^[A-Za-z0-9._:@+-]{1,128}$"
"""
The ids a channel can use for a user (e.g. a Telegram user id, a WhatsApp phone number). No `/`, so an id can be a
path segment (Starlette decodes `%2F` before routing), and no free text.
"""


class Channel(Enum):
    """
    Where a user talks to Compass.
    """
    WEB_APP = "web-app"
    """ The Compass web app (the default, for every user not created through a chat bot). """
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"


BOT_CHANNELS = [Channel.TELEGRAM, Channel.WHATSAPP]
"""
The channels that reach Compass through a chat bot and the channels API.
"""


def _validate_bot_channel(channel: Channel) -> Channel:
    if channel not in BOT_CHANNELS:
        raise ValueError(f"channel must be one of: {', '.join(c.value for c in BOT_CHANNELS)}")
    return channel


def _validate_channel_user_id(channel_user_id: str) -> str:
    # `.` and `..` match the pattern, but clients resolve them in a URL path. Not in the pattern: lookarounds are not
    # supported by pydantic's regex engine.
    if channel_user_id in (".", ".."):
        raise ValueError("channel_user_id cannot be '.' or '..'")
    return channel_user_id


class InitializeConversationRequest(BaseModel):
    channel: Channel = Field(description="The chat channel of the user: telegram or whatsapp.")
    channel_user_id: str = Field(pattern=CHANNEL_USER_ID_PATTERN,
                                 description="The id of the user on the channel (e.g. the Telegram user id). "
                                             "1 to 128 characters: letters, digits and . _ : @ + -")

    _check_channel = field_validator("channel")(_validate_bot_channel)
    _check_channel_user_id = field_validator("channel_user_id")(_validate_channel_user_id)

    class Config:
        extra = "forbid"
        str_strip_whitespace = True


class IncomingMessage(BaseModel):
    """
    A message the user sent on the channel: typed text, or a command.
    """
    channel: Channel = Field(description="The chat channel of the user: telegram or whatsapp.")
    channel_user_id: str = Field(pattern=CHANNEL_USER_ID_PATTERN,
                                 description="The id of the user on the channel (e.g. the Telegram user id).")
    text: Optional[str] = Field(default=None, max_length=MAX_MESSAGE_LENGTH,
                                description="The text the user typed, or the choice they tapped.")
    command: Optional[str] = Field(default=None, max_length=64,
                                   description="The command the user sent, e.g. /start, /restart, /report.")

    _check_channel = field_validator("channel")(_validate_bot_channel)
    _check_channel_user_id = field_validator("channel_user_id")(_validate_channel_user_id)

    class Config:
        extra = "forbid"
        str_strip_whitespace = True


class Document(BaseModel):
    """
    A file sent to the user, e.g. the skills report PDF.
    """
    file_name: str
    content_type: str
    url: str


class OutgoingMessage(BaseModel):
    """
    A message for the bot to send to the user.
    """
    text: str
    choices: list[str] = Field(default_factory=list,
                               description="Buttons to show, where the channel supports them. Tapping one sends "
                                           "its text back as the text of the next message.")
    document: Optional[Document] = None
