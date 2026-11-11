from typing import Awaitable

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.channels.bws_renderer import BwsAlternative, BwsTask
from app.channels.repository import ChannelStateRepository, PendingBwsAnswer
from app.channels.types import Channel
from app.server_dependencies.database_collections import Collections


@pytest.fixture(scope="function")
async def get_db(in_memory_application_database) -> AsyncIOMotorDatabase:
    return await in_memory_application_database


def _pending(session_id: int = 1, task_id: str = "0", best_letter: str | None = None) -> PendingBwsAnswer:
    return PendingBwsAnswer(session_id=session_id,
                            task=BwsTask(task_id=task_id,
                                         alternatives=[BwsAlternative(wa_id="wa.a", label="Analysing data"),
                                                       BwsAlternative(wa_id="wa.b", label="Helping people")]),
                            best_letter=best_letter)


async def _count_docs(db: AsyncIOMotorDatabase) -> int:
    return await db.get_collection(Collections.CHANNEL_PENDING_BWS_ANSWERS).count_documents({})


@pytest.mark.asyncio
class TestGetPendingBwsAnswer:
    async def test_no_pending_answer(self, get_db: Awaitable[AsyncIOMotorDatabase]):
        # GIVEN a session with no pending BWS answer
        repository = ChannelStateRepository(await get_db)

        # WHEN getting its pending answer
        actual = await repository.get_pending_bws_answer(1)

        # THEN there is none
        assert actual is None

    async def test_gets_the_pending_answer_of_the_session(self, get_db: Awaitable[AsyncIOMotorDatabase]):
        # GIVEN the pending answers of two sessions
        repository = ChannelStateRepository(await get_db)
        given_pending = _pending(session_id=1, best_letter="B")
        await repository.save_pending_bws_answer(given_pending)
        await repository.save_pending_bws_answer(_pending(session_id=2, task_id="5"))

        # WHEN getting the pending answer of the first session
        actual = await repository.get_pending_bws_answer(1)

        # THEN it is the one saved for that session, with its task and the letter picked so far
        assert actual == given_pending

    async def test_database_error_is_raised(self, get_db: Awaitable[AsyncIOMotorDatabase], mocker):
        # GIVEN the database fails
        repository = ChannelStateRepository(await get_db)
        mocker.patch.object(repository._collection, "find_one",  # pylint: disable=protected-access
                            side_effect=Exception("Database error"))

        # WHEN getting a pending answer
        # THEN the error is raised
        with pytest.raises(Exception, match="Database error"):
            await repository.get_pending_bws_answer(1)


@pytest.mark.asyncio
class TestSavePendingBwsAnswer:
    async def test_replaces_the_pending_answer_of_the_session(self, get_db: Awaitable[AsyncIOMotorDatabase]):
        # GIVEN a session with a pending answer
        db = await get_db
        repository = ChannelStateRepository(db)
        await repository.save_pending_bws_answer(_pending(session_id=1))

        # WHEN the user picks the most liked option, and the pending answer is saved again
        given_pending = _pending(session_id=1, best_letter="A")
        await repository.save_pending_bws_answer(given_pending)

        # THEN the session has only the new pending answer
        assert await repository.get_pending_bws_answer(1) == given_pending
        assert await _count_docs(db) == 1

    async def test_replaces_the_task_of_the_session(self, get_db: Awaitable[AsyncIOMotorDatabase]):
        # GIVEN a session with a pending answer for a task
        db = await get_db
        repository = ChannelStateRepository(db)
        await repository.save_pending_bws_answer(_pending(session_id=1, task_id="0", best_letter="A"))

        # WHEN the next task is saved
        given_pending = _pending(session_id=1, task_id="1")
        await repository.save_pending_bws_answer(given_pending)

        # THEN the session has only the next task, with no letter picked yet
        assert await repository.get_pending_bws_answer(1) == given_pending
        assert await _count_docs(db) == 1


@pytest.mark.asyncio
class TestDeletePendingBwsAnswer:
    async def test_deletes_only_the_pending_answer_of_the_session(self, get_db: Awaitable[AsyncIOMotorDatabase]):
        # GIVEN the pending answers of two sessions
        repository = ChannelStateRepository(await get_db)
        await repository.save_pending_bws_answer(_pending(session_id=1))
        given_other_pending = _pending(session_id=2)
        await repository.save_pending_bws_answer(given_other_pending)

        # WHEN the pending answer of the first session is deleted
        await repository.delete_pending_bws_answer(1)

        # THEN the first session has no pending answer
        assert await repository.get_pending_bws_answer(1) is None
        # AND the other session keeps its pending answer
        assert await repository.get_pending_bws_answer(2) == given_other_pending

    async def test_deleting_a_missing_pending_answer_does_nothing(self, get_db: Awaitable[AsyncIOMotorDatabase]):
        # GIVEN a session with no pending answer
        repository = ChannelStateRepository(await get_db)

        # WHEN its pending answer is deleted
        await repository.delete_pending_bws_answer(1)

        # THEN nothing fails, and there is still no pending answer
        assert await repository.get_pending_bws_answer(1) is None


@pytest.mark.asyncio
class TestRecordReceivedUpdate:
    async def test_records_an_update_once(self, get_db: Awaitable[AsyncIOMotorDatabase]):
        # GIVEN an update a bot received
        repository = ChannelStateRepository(await get_db)
        given_update_id = 1001

        # WHEN it is recorded, then recorded again (the channel sent it again)
        first = await repository.record_received_update(Channel.TELEGRAM, given_update_id)
        second = await repository.record_received_update(Channel.TELEGRAM, given_update_id)

        # THEN it is new the first time only
        assert first is True
        assert second is False

    async def test_the_same_id_on_another_channel_is_another_update(self,
                                                                    get_db: Awaitable[AsyncIOMotorDatabase]):
        # GIVEN an update received on Telegram
        repository = ChannelStateRepository(await get_db)
        await repository.record_received_update(Channel.TELEGRAM, 1002)

        # WHEN an update with the same id is received on WhatsApp
        actual = await repository.record_received_update(Channel.WHATSAPP, 1002)

        # THEN it is a new update
        assert actual is True
