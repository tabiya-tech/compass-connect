import asyncio

import pytest

from app.integration.webhooks.sending_loop import send_due_webhooks


class _FakeNotifier:
    """
    Answers `attempt()` from a script of rounds: in each round, how many deliveries are due. A round that is an
    exception fails instead. After the script, nothing is due.
    """

    def __init__(self, *rounds):
        self._rounds = list(rounds)
        self._due_now = 0
        self.sent = 0
        self.attempts = 0
        self.rounds_done = asyncio.Event()

    async def attempt(self) -> bool:
        self.attempts += 1
        if self._due_now == 0:
            if not self._rounds:
                self.rounds_done.set()
                return False
            next_round = self._rounds.pop(0)
            if isinstance(next_round, Exception):
                raise next_round
            self._due_now = next_round
            if self._due_now == 0:
                return False
        self._due_now -= 1
        self.sent += 1
        return True


async def _run_until_the_script_is_done(notifier: _FakeNotifier) -> None:
    loop = asyncio.create_task(send_due_webhooks(notifier, poll_interval_seconds=0.001))  # type: ignore[arg-type]
    await asyncio.wait_for(notifier.rounds_done.wait(), timeout=5)
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop


@pytest.mark.asyncio
async def test_sends_everything_due_in_each_round():
    # GIVEN 3 deliveries due, then none, then 2
    notifier = _FakeNotifier(3, 0, 2)

    # WHEN the loop runs through these rounds
    await _run_until_the_script_is_done(notifier)

    # THEN all 5 are sent
    assert notifier.sent == 5


@pytest.mark.asyncio
async def test_keeps_running_after_a_failed_round():
    # GIVEN a round that fails (e.g. the database is not reachable), then a delivery due
    notifier = _FakeNotifier(RuntimeError("database down"), 1)

    # WHEN the loop runs
    await _run_until_the_script_is_done(notifier)

    # THEN the next round still sends it
    assert notifier.sent == 1


@pytest.mark.asyncio
async def test_stops_when_cancelled():
    # GIVEN the loop running with nothing due
    notifier = _FakeNotifier()
    loop = asyncio.create_task(send_due_webhooks(notifier, poll_interval_seconds=0.001))  # type: ignore[arg-type]
    await asyncio.wait_for(notifier.rounds_done.wait(), timeout=5)

    # WHEN it is cancelled (on shutdown)
    loop.cancel()

    # THEN it stops
    with pytest.raises(asyncio.CancelledError):
        await loop
    assert loop.cancelled()
