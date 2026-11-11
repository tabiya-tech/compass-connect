from enum import Enum
from typing import Optional

from pydantic import BaseModel


class EventKind(Enum):
    TEXT = "text"
    """ The user typed text, or tapped a choice. """
    COMMAND = "command"
    """ The user sent a command, e.g. /start or /restart. """
    UNSUPPORTED = "unsupported"
    """ The user sent something the bot cannot forward, e.g. a photo or a voice message. """


class IncomingEvent(BaseModel):
    """
    Something a user did on a channel, in a form that is the same for every channel.

    Each channel turns its own updates (Telegram updates, WhatsApp webhooks, ...) into these events.
    """
    kind: EventKind
    user_id: str
    """ The id of the user on the channel, e.g. the Telegram user id. """
    text: Optional[str] = None
    """ The text for TEXT, the command (e.g. "/restart") for COMMAND, otherwise None. """
