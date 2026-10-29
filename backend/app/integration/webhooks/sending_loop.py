"""
The loop that sends the webhook notifications: the first attempts and the retries. Started by the server's lifespan
when webhooks are enabled, and cancelled on shutdown.
"""

import asyncio
import logging

from app.integration.webhooks.notifier import WebhookNotifier

POLL_INTERVAL_SECONDS = 10
"""
How long the loop waits when nothing is due: a platform hears about a completed conversation within about that long.
"""

_logger = logging.getLogger(__name__)


async def send_due_webhooks(notifier: WebhookNotifier, poll_interval_seconds: float = POLL_INTERVAL_SECONDS) -> None:
    """
    Send the deliveries that are due, wait, and again, until cancelled. A cancelled attempt keeps its delivery held
    until the lease is over, then it is attempted again.
    """
    while True:
        try:
            while await notifier.attempt():
                pass
        except Exception:  # pylint: disable=broad-except
            # e.g. the database is not reachable: the loop must keep running, the next round tries again
            _logger.exception("Could not send the due webhook deliveries")
        await asyncio.sleep(poll_interval_seconds)
