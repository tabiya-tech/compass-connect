from abc import ABC, abstractmethod
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.channels.bws_renderer import BwsTask
from app.server_dependencies.database_collections import Collections


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


class ChannelStateRepository(IChannelStateRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        self._collection = db.get_collection(Collections.CHANNEL_PENDING_BWS_ANSWERS)

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
