"""
Turns Telegram updates into `IncomingEvent`s, and choices into Telegram keyboards.
"""
from typing import Optional, Union

from telegram import BotCommand, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ChatType

from app.channels.bots.events import EventKind, IncomingEvent

COMMANDS = [
    BotCommand("start", "Start, or continue where you left off"),
    BotCommand("restart", "Start a new conversation"),
    BotCommand("report", "Get your skills report"),
    BotCommand("help", "Show what I can do"),
]
""" The command menu of the bot. """

_SHORT_CHOICE_LENGTH = 4
""" Choices up to this long (e.g. the letters of a best-worst task) share a row. """

_SHORT_CHOICES_PER_ROW = 3


def to_incoming_event(update: Update) -> Optional[IncomingEvent]:
    """
    :return: The event for the update, or None for updates the bot ignores (e.g. groups, edited messages).
    """
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None or chat.type != ChatType.PRIVATE:
        return None
    user_id = str(user.id)

    # Only new messages: an edited message cannot change what Compass already answered.
    message = update.message
    if message is None:
        return None
    if message.text is None:
        return IncomingEvent(kind=EventKind.UNSUPPORTED, user_id=user_id)

    text = message.text.strip()
    if text.startswith("/"):
        # "/start@CompassBot arguments" -> "/start"
        command = "/" + text[1:].split(maxsplit=1)[0].split("@", 1)[0].lower() if len(text) > 1 else "/"
        return IncomingEvent(kind=EventKind.COMMAND, user_id=user_id, text=command)
    return IncomingEvent(kind=EventKind.TEXT, user_id=user_id, text=text)


def build_reply_markup(choices: Optional[list[str]]) -> Union[ReplyKeyboardMarkup, ReplyKeyboardRemove, None]:
    """
    The keyboard for the choices: tapping a button sends its text, like typing it.

    :param choices: The choices. An empty list removes the keyboard. None leaves the keyboard as it is.
    """
    if choices is None:
        return None
    if not choices:
        return ReplyKeyboardRemove()

    per_row = _SHORT_CHOICES_PER_ROW if all(len(choice) <= _SHORT_CHOICE_LENGTH for choice in choices) else 1
    rows = [[KeyboardButton(choice) for choice in choices[start:start + per_row]]
            for start in range(0, len(choices), per_row)]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)
