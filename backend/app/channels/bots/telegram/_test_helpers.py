from datetime import datetime, timezone
from typing import Optional

from telegram import Chat, Message, PhotoSize, Update, User
from telegram.constants import ChatType

USER = User(id=42, first_name="Test", is_bot=False)


def _chat(chat_type: str) -> Chat:
    return Chat(id=USER.id if chat_type == ChatType.PRIVATE else -100, type=chat_type)


def _message(text: Optional[str] = None, chat_type: str = ChatType.PRIVATE, **kwargs) -> Message:
    return Message(message_id=1, date=datetime.now(timezone.utc), chat=_chat(chat_type), from_user=USER, text=text,
                   **kwargs)


def text_update(text: str, chat_type: str = ChatType.PRIVATE) -> Update:
    return Update(update_id=1, message=_message(text, chat_type))


def photo_update() -> Update:
    return Update(update_id=1, message=_message(photo=(PhotoSize("file", "unique", 10, 10),)))


def edited_text_update(text: str) -> Update:
    return Update(update_id=1, edited_message=_message(text))
