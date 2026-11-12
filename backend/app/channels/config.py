"""
The per-deployment settings of the channels: the channels API (/api/channels/**) and the chat bots.

- BACKEND_ENABLE_CHANNELS: "true" registers the /api/channels/** routes. Off by default.
- BACKEND_ENABLE_TELEGRAM_BOT: "true" also runs the Telegram bot. Needs BACKEND_ENABLE_CHANNELS, and the
  BACKEND_TELEGRAM_* settings, see `parse_telegram_config`.
"""
from typing import Optional

from pydantic import BaseModel

from app.channels.bots.telegram.config import TelegramConfig, parse_telegram_config
from app.channels.types import Channel

SLOW_TURN_THRESHOLD_SECONDS = 30.0
""" A turn of a channel user that takes longer is reported to Sentry as a slow turn. """


class ChannelsConfig(BaseModel):
    """
    The channels settings of the application.
    """
    enabled: bool = False
    """ Whether the /api/channels/** routes exist. """

    telegram: Optional[TelegramConfig] = None
    """ The Telegram bot, or None when it does not run. """

    @property
    def enabled_bots(self) -> list[Channel]:
        return [Channel.TELEGRAM] if self.telegram is not None else []


def _is_true(value: Optional[str]) -> bool:
    return (value or "").strip().lower() == "true"


def parse_channels_config(*,
                          enable_channels: Optional[str],
                          enable_telegram_bot: Optional[str],
                          telegram_bot_token: Optional[str],
                          telegram_webhook_secret: Optional[str],
                          telegram_webhook_url: Optional[str],
                          backend_url: Optional[str]) -> ChannelsConfig:
    """
    Build the channels settings from the environment variables.

    :param enable_channels: BACKEND_ENABLE_CHANNELS
    :param enable_telegram_bot: BACKEND_ENABLE_TELEGRAM_BOT
    :param telegram_bot_token: BACKEND_TELEGRAM_BOT_TOKEN
    :param telegram_webhook_secret: BACKEND_TELEGRAM_WEBHOOK_SECRET
    :param telegram_webhook_url: BACKEND_TELEGRAM_WEBHOOK_URL
    :param backend_url: BACKEND_URL, to derive the URL of the webhook
    :raises ValueError: if the settings are not valid. The backend does not start without the bot the deployment asked
        for.
    """
    channels_enabled = _is_true(enable_channels)
    telegram_enabled = _is_true(enable_telegram_bot)

    if telegram_enabled and not channels_enabled:
        raise ValueError("BACKEND_ENABLE_TELEGRAM_BOT needs BACKEND_ENABLE_CHANNELS=true")
    if not channels_enabled:
        return ChannelsConfig(enabled=False)

    telegram: Optional[TelegramConfig] = None
    if telegram_enabled:
        telegram = parse_telegram_config(bot_token=telegram_bot_token,
                                         webhook_secret=telegram_webhook_secret,
                                         webhook_url=telegram_webhook_url,
                                         backend_url=backend_url)
    return ChannelsConfig(enabled=True, telegram=telegram)
