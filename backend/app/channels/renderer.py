from abc import ABC, abstractmethod
from typing import Mapping, Optional

from app.channels.types import OutgoingMessage
from app.conversations.types import ConversationMessage, ConversationMessageSender, ConversationMessageType, \
    ConversationResponse
from app.i18n.translation_service import t


class IRenderer(ABC):
    """
    Renders a Compass message of one message type as a message a chat bot can send.
    """

    @abstractmethod
    def render(self, message: ConversationMessage) -> Optional[OutgoingMessage]:
        """
        :return: the message for the bot to send, or None if this renderer cannot render the message (the conversation
            renderer then falls back to the text renderer)
        """
        raise NotImplementedError()


class TextRenderer(IRenderer):
    """
    Renders a message as its text, and its quick reply options as choices. Renders TEXT messages, and is the fallback
    for a message no other renderer can render.
    """

    def render(self, message: ConversationMessage) -> Optional[OutgoingMessage]:
        # tapping a choice sends its label, the same input as clicking the quick reply in the web app
        return OutgoingMessage(text=message.message,
                               choices=[option.label for option in message.quick_reply_options or []])


def get_compass_messages(response: ConversationResponse) -> list[ConversationMessage]:
    """
    :return: the messages of Compass in the response, in order, without the messages of the user
    """
    return [message for message in response.messages if message.sender == ConversationMessageSender.COMPASS]


class ConversationRenderer:
    """
    Renders the Compass messages of a conversation turn, each with the renderer of its message type.
    """

    def __init__(self, renderers: Mapping[ConversationMessageType, IRenderer], fallback: Optional[IRenderer] = None):
        """
        :param renderers: the renderer of each message type, e.g. {ConversationMessageType.TEXT: TextRenderer()}
        :param fallback: the renderer of a message no renderer can render, the text renderer by default
        """
        self._renderers = renderers
        self._fallback = fallback or TextRenderer()

    def render(self, response: ConversationResponse) -> list[OutgoingMessage]:
        """
        :return: the messages to send, in order. When the conversation is completed, a last message tells the user
            what they can do next.
        """
        rendered = [self._render_message(message) for message in get_compass_messages(response)]
        if response.conversation_completed:
            rendered.append(OutgoingMessage(text=t("messages", "channels.conversationCompleted")))
        return rendered

    def _render_message(self, message: ConversationMessage) -> OutgoingMessage:
        renderer = self._renderers.get(message.message_type)
        rendered = renderer.render(message) if renderer is not None else None
        return rendered if rendered is not None else self._fallback.render(message)
