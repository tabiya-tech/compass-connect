from typing import Optional

import pytest
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ChatType

from app.channels.bots.events import EventKind, IncomingEvent
from app.channels.bots.telegram.mapping import build_reply_markup, to_incoming_event
from app.channels.bots.telegram._test_helpers import edited_text_update, photo_update, text_update

USER_ID = "42"


class TestToIncomingEvent:
    @pytest.mark.parametrize("given_update, expected", [
        pytest.param(text_update("I fixed phones"),
                     IncomingEvent(kind=EventKind.TEXT, user_id=USER_ID, text="I fixed phones"),
                     id="text"),
        pytest.param(text_update("  Yes  "), IncomingEvent(kind=EventKind.TEXT, user_id=USER_ID, text="Yes"),
                     id="text is stripped"),
        pytest.param(text_update("/start"), IncomingEvent(kind=EventKind.COMMAND, user_id=USER_ID, text="/start"),
                     id="/start"),
        pytest.param(text_update("/start@CompassBot payload"),
                     IncomingEvent(kind=EventKind.COMMAND, user_id=USER_ID, text="/start"),
                     id="/start with bot name and payload"),
        pytest.param(text_update("/Restart"),
                     IncomingEvent(kind=EventKind.COMMAND, user_id=USER_ID, text="/restart"),
                     id="other command, lower-cased"),
        pytest.param(text_update("/report@CompassBot"),
                     IncomingEvent(kind=EventKind.COMMAND, user_id=USER_ID, text="/report"),
                     id="command with bot name"),
        pytest.param(photo_update(), IncomingEvent(kind=EventKind.UNSUPPORTED, user_id=USER_ID), id="photo"),
        pytest.param(edited_text_update("edited"), None, id="edited message is ignored"),
        pytest.param(text_update("hello", chat_type=ChatType.GROUP), None, id="group message is ignored"),
    ])
    def test_to_incoming_event(self, given_update: Update, expected: Optional[IncomingEvent]):
        # WHEN the update is mapped
        actual = to_incoming_event(given_update)

        # THEN it becomes the expected event
        assert actual == expected


class TestBuildReplyMarkup:
    def test_none_leaves_the_keyboard(self):
        assert build_reply_markup(None) is None

    def test_no_choices_removes_the_keyboard(self):
        assert isinstance(build_reply_markup([]), ReplyKeyboardRemove)

    @pytest.mark.parametrize("given_choices, expected_rows", [
        pytest.param(["A", "B", "C", "D", "E"], [["A", "B", "C"], ["D", "E"]], id="short choices share rows of 3"),
        pytest.param(["Yes, that's right", "No"], [["Yes, that's right"], ["No"]], id="long choices one per row"),
    ])
    def test_choices_become_keyboard_buttons(self, given_choices: list[str], expected_rows: list[list[str]]):
        # WHEN the keyboard is built
        actual = build_reply_markup(given_choices)

        # THEN each choice is a button that sends its text, in rows
        assert isinstance(actual, ReplyKeyboardMarkup)
        assert [[button.text for button in row] for row in actual.keyboard] == expected_rows
        # AND the keyboard hides once a button is tapped
        assert actual.one_time_keyboard and actual.resize_keyboard
