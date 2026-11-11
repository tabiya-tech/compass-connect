from abc import ABC, abstractmethod
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from app.channels.bws_renderer import BwsTask
from app.channels.types import Channel
from app.server_dependencies.database_collections import Collections
from common_libs.time_utilities import get_now


class PendingBwsAnswer(BaseModel):
    """
    A BWS task shown to the user on a channel, and their answer so far.
    """
    session_id: int
    task: BwsTask
    best_letter: Optional[str] = None
    """ The letter of the option the user likes most, once they picked it. """


class IChannelStateRepository(ABC):
    """
    Interface for the state of the channel conversations

    Allows to mock the repository in tests.
    """

    @abstractmethod
    async def get_pending_bws_answer(self, session_id: int) -> Optional[PendingBwsAnswer]:
        """
        :return: the BWS task of the session waiting for an answer, or None
        :raises Exception: if any database error occurs
        """
        raise NotImplementedError()

    @abstractmethod
    async def save_pending_bws_answer(self, pending: PendingBwsAnswer) -> None:
        """
        Save the BWS task of the session waiting for an answer, replacing the previous one.

        :raises Exception: if any database error occurs
        """
        raise NotImplementedError()

    @abstractmethod
    async def delete_pending_bws_answer(self, session_id: int) -> None:
        """
        Forget the BWS task of the session, once it is answered or no longer open.

        :raises Exception: if any database error occurs
        """
        raise NotImplementedError()

    @abstractmethod
    async def record_received_update(self, channel: Channel, update_id: int) -> bool:
        """
        Remember that the bot received an update of the channel (e.g. a Telegram update), for a day.

        :return: True the first time, False if the update was already received (the channel sent it again)
        :raises Exception: if any database error occurs
        """
        raise NotImplementedError()


class ChannelStateRepository(IChannelStateRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        self._collection = db.get_collection(Collections.CHANNEL_PENDING_BWS_ANSWERS)
        self._received_updates = db.get_collection(Collections.CHANNEL_RECEIVED_UPDATES)

    async def get_pending_bws_answer(self, session_id: int) -> Optional[PendingBwsAnswer]:
        doc = await self._collection.find_one({"session_id": {"$eq": session_id}})
        if doc is None:
            return None
        return PendingBwsAnswer.model_validate(doc, strict=False)

    async def save_pending_bws_answer(self, pending: PendingBwsAnswer) -> None:
        await self._collection.replace_one({"session_id": {"$eq": pending.session_id}}, pending.model_dump(),
                                           upsert=True)

    async def delete_pending_bws_answer(self, session_id: int) -> None:
        await self._collection.delete_one({"session_id": {"$eq": session_id}})

    async def record_received_update(self, channel: Channel, update_id: int) -> bool:
        try:
            await self._received_updates.insert_one(
                {"channel": channel.value, "update_id": update_id, "received_at": get_now()})
            return True
        except DuplicateKeyError:
            return False
