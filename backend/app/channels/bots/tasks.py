import asyncio
import logging
from typing import Coroutine

logger = logging.getLogger(__name__)


class BackgroundTasks:
    """
    Runs the work a bot does after it answered the webhook of its channel (e.g. a conversation turn).

    Keeps a reference to every running task, so it is not garbage collected before it ends, and logs the tasks that
    fail. On shutdown, waits for the running tasks so that the users still get their replies.
    """

    def __init__(self):
        self._tasks: set[asyncio.Task] = set()

    def run(self, coroutine: Coroutine, *, name: str) -> asyncio.Task:
        task = asyncio.create_task(coroutine, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    @property
    def running(self) -> int:
        return len(self._tasks)

    async def wait(self, timeout_seconds: float) -> None:
        """
        Wait for the running tasks to end, and cancel the ones still running after the timeout.
        """
        if not self._tasks:
            return
        logger.info("Waiting for %s background tasks to end", len(self._tasks))
        _, pending = await asyncio.wait(set(self._tasks), timeout=timeout_seconds)
        for task in pending:
            task.cancel()
        if pending:
            logger.warning("Cancelled %s background tasks still running after %ss", len(pending), timeout_seconds)

    def _on_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("The background task %s failed", task.get_name(), exc_info=task.exception())
