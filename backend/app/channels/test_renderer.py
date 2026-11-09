from typing import Optional

import pytest

from app.channels.renderer import ConversationRenderer, IRenderer, TextRenderer
from app.channels.types import OutgoingMessage
from app.context_vars import user_language_ctx_var
from app.conversations.types import ConversationMessage, ConversationMessageSender, ConversationMessageType, \
    ConversationPhaseResponse, ConversationResponse, CurrentConversationPhaseResponse, QuickReplyOption
from app.i18n.translation_service import t
from app.i18n.types import Locale
from common_libs.time_utilities import get_now


@pytest.fixture(autouse=True)
def _english():
    token = user_language_ctx_var.set(Locale.EN_US)
    yield
    user_language_ctx_var.reset(token)


def _message(text: str, sender: ConversationMessageSender = ConversationMessageSender.COMPASS,
             **kwargs) -> ConversationMessage:
    return ConversationMessage(message_id="message-id", message=text, sent_at=get_now(), sender=sender, **kwargs)


def _with_type(message: ConversationMessage, message_type: str) -> ConversationMessage:
    """ A message of a type ConversationMessage does not allow (yet). """
    return ConversationMessage.model_construct(**{**message.__dict__, "message_type": message_type})


def _response(*messages: ConversationMessage, completed: bool = False) -> ConversationResponse:
    return ConversationResponse(messages=list(messages), conversation_completed=completed,
                                current_phase=ConversationPhaseResponse(
                                    percentage=50, phase=CurrentConversationPhaseResponse.COLLECT_EXPERIENCES))


class _LinkRenderer(IRenderer):
    """ A renderer that adds the link in the metadata of a message, and cannot render a message without one. """

    def render(self, message: ConversationMessage) -> Optional[OutgoingMessage]:
        if not message.metadata:
            return None
        return OutgoingMessage(text=f"{message.message} {message.metadata['url']}")


class TestTextRenderer:
    def test_text_message_becomes_text(self):
        # GIVEN a text message
        given_message = _message("Tell me about your work")

        # WHEN it is rendered
        actual = TextRenderer().render(given_message)

        # THEN the bot sends its text, with no choices
        assert actual == OutgoingMessage(text="Tell me about your work")

    def test_quick_reply_options_become_choices(self):
        # GIVEN a text message with quick reply options
        given_message = _message("Shall we start?", quick_reply_options=[QuickReplyOption(label="Yes"),
                                                                         QuickReplyOption(label="No")])

        # WHEN it is rendered
        actual = TextRenderer().render(given_message)

        # THEN the labels of the options are the choices
        assert actual == OutgoingMessage(text="Shall we start?", choices=["Yes", "No"])


class TestConversationRenderer:
    def test_renders_each_message_with_the_renderer_of_its_type(self):
        # GIVEN a renderer for text messages and another one for BWS tasks
        given_renderer = ConversationRenderer({ConversationMessageType.TEXT: TextRenderer(),
                                               ConversationMessageType.BWS_TASK: _LinkRenderer()})
        # AND a turn with a text message and a BWS task
        given_response = _response(_message("Hi", quick_reply_options=[QuickReplyOption(label="Hello")]),
                                   _message("Open this:", message_type=ConversationMessageType.BWS_TASK,
                                            metadata={"url": "https://task"}))

        # WHEN it is rendered
        actual = given_renderer.render(given_response)

        # THEN each message is rendered by the renderer of its type, in order
        assert actual == [OutgoingMessage(text="Hi", choices=["Hello"]), OutgoingMessage(text="Open this: https://task")]

    def test_unknown_message_type_falls_back_to_text(self):
        # GIVEN a message of a type no renderer is registered for (e.g. a type added later), with quick reply options
        given_message = _with_type(_message("A new kind of message",
                                            quick_reply_options=[QuickReplyOption(label="Yes")]), "VIDEO")

        # WHEN it is rendered
        actual = ConversationRenderer({ConversationMessageType.TEXT: TextRenderer()}).render(_response(given_message))

        # THEN it is rendered by the text renderer: its text, and its quick reply options as choices
        assert actual == [OutgoingMessage(text="A new kind of message", choices=["Yes"])]

    def test_message_its_renderer_cannot_render_falls_back_to_text(self):
        # GIVEN a message, with quick reply options, that the renderer of its type cannot render
        given_message = _message("Open this:", message_type=ConversationMessageType.BWS_TASK,
                                 quick_reply_options=[QuickReplyOption(label="Skip")])

        # WHEN it is rendered
        actual = ConversationRenderer({ConversationMessageType.BWS_TASK: _LinkRenderer()}).render(
            _response(given_message))

        # THEN it is rendered by the text renderer: its text, and its quick reply options as choices
        assert actual == [OutgoingMessage(text="Open this:", choices=["Skip"])]

    def test_renders_only_the_compass_messages(self):
        # GIVEN a turn with a user message and two Compass messages
        given_response = _response(_message("Hi", sender=ConversationMessageSender.USER),
                                   _message("First"), _message("Second"))

        # WHEN it is rendered
        actual = ConversationRenderer({ConversationMessageType.TEXT: TextRenderer()}).render(given_response)

        # THEN only the Compass messages are sent, in order
        assert [m.text for m in actual] == ["First", "Second"]

    def test_completed_conversation_adds_what_to_do_next(self):
        # GIVEN the last turn of a conversation
        given_response = _response(_message("Goodbye"), completed=True)

        # WHEN it is rendered
        actual = ConversationRenderer({ConversationMessageType.TEXT: TextRenderer()}).render(given_response)

        # THEN the user is told what they can do next
        assert [m.text for m in actual] == ["Goodbye", t("messages", "channels.conversationCompleted")]
