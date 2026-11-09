import json
import string
from typing import Optional

from pydantic import BaseModel, ValidationError

from app.channels.renderer import IRenderer, get_compass_messages
from app.channels.types import OutgoingMessage
from app.conversations.types import ConversationMessage, ConversationMessageType, ConversationResponse
from app.i18n.translation_service import t


class BwsAlternative(BaseModel):
    wa_id: str
    label: str


class BwsTask(BaseModel):
    """
    The part of the metadata of a BWS_TASK message the channels need.
    """
    task_id: str
    alternatives: list[BwsAlternative]

    @property
    def letters(self) -> list[str]:
        return list(string.ascii_uppercase[:len(self.alternatives)])

    def parse_letter(self, text: str) -> Optional[str]:
        """
        :return: the upper case letter of an option if the text is only that letter (e.g. "b", "B", "B."), or None
        """
        candidate = _strip_letter(text).upper()
        if candidate in self.letters:
            return candidate
        return None

    def build_answer(self, best_letter: str, worst_letter: str) -> str:
        """
        :return: the answer to the task, in the JSON format the preference elicitation agent accepts
        """
        return json.dumps({
            "type": "bws_response",
            "task_id": self.task_id,
            "best": self.alternatives[self.letters.index(best_letter)].wa_id,
            "worst": self.alternatives[self.letters.index(worst_letter)].wa_id,
        })


def is_letter(text: str) -> bool:
    """
    :return: True if the text is a single letter (e.g. "F", "f."), whether or not it is an option of a task
    """
    candidate = _strip_letter(text)
    return len(candidate) == 1 and candidate.isalpha()


def _strip_letter(text: str) -> str:
    return text.strip().rstrip(".)").strip()


class BwsRenderer(IRenderer):
    """
    Renders a BWS task: its text (it lists the options lettered A, B, C...), the "most" prompt, and the letters as
    choices. Then asks for the next steps of the task, without the task again.
    """

    def render(self, message: ConversationMessage) -> Optional[OutgoingMessage]:
        task = self.get_task(message)
        if task is None:
            return None
        return OutgoingMessage(text=f"{message.message}\n\n{t('messages', 'channels.bwsMostPrompt')}",
                               choices=task.letters)

    @staticmethod
    def render_prompt(task: BwsTask, best_letter: Optional[str]) -> OutgoingMessage:
        """
        Ask for the most liked option if the user did not pick it yet, otherwise for the least liked option, among the
        ones the user did not pick as most liked.
        """
        if best_letter is None:
            return OutgoingMessage(text=t("messages", "channels.bwsMostPrompt"), choices=task.letters)
        return OutgoingMessage(text=t("messages", "channels.bwsLeastPrompt"),
                               choices=[letter for letter in task.letters if letter != best_letter])

    @staticmethod
    def get_task(message: ConversationMessage) -> Optional[BwsTask]:
        """
        :return: the BWS task of the message, or None if the message is not a BWS task with options to letter
        """
        if message.message_type != ConversationMessageType.BWS_TASK or not message.metadata:
            return None
        try:
            task = BwsTask.model_validate(message.metadata, strict=False)
        except ValidationError:
            return None
        if not 2 <= len(task.alternatives) <= len(string.ascii_uppercase):
            return None
        return task

    @classmethod
    def get_open_task(cls, response: ConversationResponse) -> Optional[BwsTask]:
        """
        :return: the BWS task waiting for an answer, i.e. the last Compass message of the response if it is a BWS task
        """
        compass_messages = get_compass_messages(response)
        if not compass_messages:
            return None
        return cls.get_task(compass_messages[-1])
