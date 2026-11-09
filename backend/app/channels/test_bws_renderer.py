import json

import pytest

from app.channels.bws_renderer import BwsRenderer, is_letter
from app.channels.renderer import ConversationRenderer, TextRenderer
from app.channels.types import OutgoingMessage
from app.context_vars import user_language_ctx_var
from app.conversations.types import ConversationMessage, ConversationMessageSender, ConversationMessageType, \
    ConversationPhaseResponse, ConversationResponse, CurrentConversationPhaseResponse
from app.i18n.translation_service import t
from app.i18n.types import Locale
from common_libs.time_utilities import get_now

_ALTERNATIVES = [{"wa_id": "wa.a", "label": "Analysing data"},
                 {"wa_id": "wa.b", "label": "Helping people"},
                 {"wa_id": "wa.c", "label": "Repairing machines"}]


@pytest.fixture(autouse=True)
def _english():
    token = user_language_ctx_var.set(Locale.EN_US)
    yield
    user_language_ctx_var.reset(token)


def _text(key: str) -> str:
    return t("messages", f"channels.{key}")


def _message(text: str, **kwargs) -> ConversationMessage:
    return ConversationMessage(message_id="message-id", message=text, sent_at=get_now(),
                               sender=ConversationMessageSender.COMPASS, **kwargs)


def _bws_message(alternatives: list[dict] | None = None) -> ConversationMessage:
    return _message("Question 1 of 8", message_type=ConversationMessageType.BWS_TASK,
                    metadata={"task_id": "3", "task_number": 4, "total_tasks": 8,
                              "alternatives": _ALTERNATIVES if alternatives is None else alternatives,
                              "quick_reply_options": [{"label": "Skip"}]})


def _response(*messages: ConversationMessage) -> ConversationResponse:
    return ConversationResponse(messages=list(messages),
                                current_phase=ConversationPhaseResponse(
                                    percentage=50, phase=CurrentConversationPhaseResponse.PREFERENCE_ELICITATION))


def _task():
    return BwsRenderer.get_task(_bws_message())


class TestBwsRenderer:
    def test_bws_task_becomes_lettered_choices_with_the_most_prompt(self):
        # GIVEN a BWS task (its text lists the options lettered A, B, C)
        # WHEN it is rendered
        actual = BwsRenderer().render(_bws_message())

        # THEN the bot sends the task, asks for the most liked option, and the letters are the choices
        assert actual == OutgoingMessage(text="Question 1 of 8\n\n" + _text("bwsMostPrompt"), choices=["A", "B", "C"])

    @pytest.mark.parametrize("given_alternatives", [[], [{"wa_id": "wa.a"}]],
                             ids=["no alternatives", "an alternative without a label"])
    def test_bws_task_that_cannot_be_lettered_is_not_rendered(self, given_alternatives: list[dict]):
        # GIVEN a BWS task without valid alternatives
        # WHEN it is rendered
        actual = BwsRenderer().render(_bws_message(given_alternatives))

        # THEN the BWS renderer cannot render it
        assert actual is None

    def test_bws_task_that_cannot_be_lettered_falls_back_to_text_in_a_conversation(self):
        # GIVEN a BWS task without alternatives in a conversation turn
        given_renderer = ConversationRenderer({ConversationMessageType.TEXT: TextRenderer(),
                                               ConversationMessageType.BWS_TASK: BwsRenderer()})

        # WHEN it is rendered
        actual = given_renderer.render(_response(_bws_message([])))

        # THEN it is rendered by the text renderer: its text, with no choices as it has no quick reply options
        assert actual == [OutgoingMessage(text="Question 1 of 8")]

    def test_prompts(self):
        # GIVEN a task with options A, B, C
        given_task = _task()

        # WHEN the next step is asked
        # THEN before the most liked option is picked, every letter is a choice
        assert BwsRenderer.render_prompt(given_task, None) == OutgoingMessage(text=_text("bwsMostPrompt"),
                                                                              choices=["A", "B", "C"])
        # AND after, every other letter is a choice for the least liked option
        assert BwsRenderer.render_prompt(given_task, "B") == OutgoingMessage(text=_text("bwsLeastPrompt"),
                                                                             choices=["A", "C"])

    def test_open_task_is_the_last_message(self):
        # GIVEN a turn that ends with a BWS task
        # WHEN the open task is read
        actual = BwsRenderer.get_open_task(_response(_message("Great!"), _bws_message()))

        # THEN it is the task, with a letter per option
        assert actual.task_id == "3"
        assert actual.letters == ["A", "B", "C"]
        # AND a turn that ends with a text has no open task
        assert BwsRenderer.get_open_task(_response(_bws_message(), _message("Thanks"))) is None


class TestBwsTask:
    @pytest.mark.parametrize("given_text, expected_letter", [
        ("A", "A"), ("b", "B"), (" C. ", "C"), ("c)", "C"), ("D", None), ("AB", None), ("most A", None)])
    def test_parse_letter(self, given_text: str, expected_letter: str | None):
        # GIVEN a task with options A, B, C
        # WHEN the text of the user is parsed
        # THEN only a letter of an option is a letter
        assert _task().parse_letter(given_text) == expected_letter

    @pytest.mark.parametrize("given_text, expected", [("F", True), ("f.", True), ("AB", False), ("1", False)])
    def test_is_letter(self, given_text: str, expected: bool):
        # GIVEN a text WHEN it is checked THEN only a single letter is a letter
        assert is_letter(given_text) == expected

    def test_letters_map_back_to_the_json_answer(self):
        # GIVEN a task with options A, B, C
        # WHEN the user likes B most and A least
        actual = _task().build_answer("B", "A")

        # THEN the answer is the JSON the preference elicitation agent accepts, with the ids of the options
        assert json.loads(actual) == {"type": "bws_response", "task_id": "3", "best": "wa.b", "worst": "wa.a"}
