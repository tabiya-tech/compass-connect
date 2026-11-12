"""
How the channels show up in Sentry and in the logs, so that their events can be grouped by channel (which bot) and by
what the channel was doing, and alerted on.

Sentry tags, on every event raised while a channel works:
- `channel`: the bot, e.g. "telegram"
- `channel_kind`: "bot", for every bot. The web app sets no channel tags.
- `channel_operation`: a `ChannelOperation`, e.g. "conversation_message"

Events meant for alert rules (see docs/channels/operations.md):
- gateway errors: a channel turn or a bot call that failed, tagged `channel_gateway_error:true`, grouped by channel and
  operation
- slow turns: a turn that took longer than `SLOW_TURN_THRESHOLD_SECONDS`, tagged `channel_slow_turn:true`, grouped by
  channel
"""
import logging
from enum import Enum

import sentry_sdk

from app.channels.types import Channel
from app.context_vars import channel_ctx_var, channel_operation_ctx_var

logger = logging.getLogger(__name__)

TAG_CHANNEL = "channel"
TAG_CHANNEL_KIND = "channel_kind"
TAG_CHANNEL_OPERATION = "channel_operation"
TAG_GATEWAY_ERROR = "channel_gateway_error"
TAG_SLOW_TURN = "channel_slow_turn"

class ChannelKind(Enum):
    """
    The kind of a channel, for the `channel_kind` tag.
    """
    BOT = "bot"
    """ A chat bot, e.g. Telegram. """


class ChannelOperation(Enum):
    """
    What a channel is doing.
    """
    WEBHOOK = "webhook"
    """ A bot receives an update from its channel, before it knows what the user did. """
    INITIALIZE_CONVERSATION = "initialize_conversation"
    """ The first contact of a user: their anonymous Compass user and their conversation are created or found. """
    CONVERSATION_MESSAGE = "conversation_message"
    """ The user sent a text (or tapped a choice) for their conversation: a conversation turn. """
    COMMAND = "command"
    """ The user sent a command, e.g. /start or /restart. """
    BOT_REGISTRATION = "bot_registration"
    """ A bot registers itself with its channel when the backend starts (webhook, command menu). """


def set_channel_context(channel: Channel, operation: ChannelOperation) -> None:
    """
    Tag the current work with the channel and the operation: the metric events (see `AbstractCompassMetricEvent`), and
    the Sentry events of the current isolation scope.

    Work that runs outside a request (e.g. a bot's background task) must run in its own
    `sentry_sdk.isolation_scope()`, so that the tags do not reach the events of other work.
    """
    channel_ctx_var.set(channel)
    channel_operation_ctx_var.set(operation)

    scope = sentry_sdk.get_isolation_scope()
    scope.set_tag(TAG_CHANNEL, channel.value)
    scope.set_tag(TAG_CHANNEL_KIND, ChannelKind.BOT.value)
    scope.set_tag(TAG_CHANNEL_OPERATION, operation.value)


def capture_gateway_error(error: BaseException) -> None:
    """
    Report an error of a channel to Sentry, grouped by channel and operation, for the "gateway errors" alert.

    Call it before logging the error with `logger.exception`: Sentry drops the second capture of the same exception.
    """
    channel = channel_ctx_var.get()
    operation = channel_operation_ctx_var.get()
    with sentry_sdk.new_scope() as scope:
        scope.set_tag(TAG_GATEWAY_ERROR, "true")
        scope.fingerprint = ["channel-gateway-error", channel.value if channel else "unknown",
                             operation.value if operation else "unknown", type(error).__name__]
        sentry_sdk.capture_exception(error)


def report_turn_duration(*, channel: Channel, duration_seconds: float, threshold_seconds: float) -> bool:
    """
    Report a turn that took longer than the threshold, as a Sentry warning grouped by channel, for the "slow turns"
    alert.

    :return: whether the turn was slow
    """
    if duration_seconds <= threshold_seconds:
        return False

    logger.warning("Slow %s turn: %.1fs, above %.1fs", channel.value, duration_seconds, threshold_seconds)
    with sentry_sdk.new_scope() as scope:
        scope.set_tag(TAG_SLOW_TURN, "true")
        scope.set_context("channel_turn", {"duration_seconds": round(duration_seconds, 3),
                                           "threshold_seconds": threshold_seconds})
        scope.fingerprint = ["channel-slow-turn", channel.value]
        sentry_sdk.capture_message(f"Slow {channel.value} turn", level="warning")
    return True
