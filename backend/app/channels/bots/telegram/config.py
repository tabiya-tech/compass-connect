import re
from typing import Optional

from pydantic import BaseModel

WEBHOOK_PATH = "/api/channels/telegram/webhook"
""" The path Telegram sends the updates to. """

_WEBHOOK_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
""" The secret tokens Telegram accepts (see https://core.telegram.org/bots/api#setwebhook). """


class TelegramConfig(BaseModel):
    bot_token: str
    """ The token of the bot, from @BotFather. """

    webhook_secret: str
    """ Telegram sends it with every update, in the X-Telegram-Bot-Api-Secret-Token header. """

    webhook_url: str
    """ The public HTTPS URL of the webhook. """


def parse_telegram_config(*,
                          bot_token: Optional[str],
                          webhook_secret: Optional[str],
                          webhook_url: Optional[str],
                          backend_url: Optional[str]) -> TelegramConfig:
    """
    Build the settings of the Telegram bot, when BACKEND_ENABLE_TELEGRAM_BOT is true, from the environment variables:
    - BACKEND_TELEGRAM_BOT_TOKEN: required, the token of the bot.
    - BACKEND_TELEGRAM_WEBHOOK_SECRET: required, 1 to 256 characters: letters, digits, _ and -.
    - BACKEND_TELEGRAM_WEBHOOK_URL: optional, {backend_url}/api/channels/telegram/webhook by default. Locally, the URL
      of an HTTPS tunnel to the backend.

    :raises ValueError: if the settings are not valid
    """
    bot_token = (bot_token or "").strip()
    if not bot_token:
        raise ValueError("BACKEND_TELEGRAM_BOT_TOKEN must be set when BACKEND_ENABLE_TELEGRAM_BOT is true")

    webhook_secret = (webhook_secret or "").strip()
    if not _WEBHOOK_SECRET_PATTERN.fullmatch(webhook_secret):
        raise ValueError("BACKEND_TELEGRAM_WEBHOOK_SECRET must be set when BACKEND_ENABLE_TELEGRAM_BOT is true: 1 to "
                         "256 characters, letters, digits, _ and -")

    webhook_url = (webhook_url or "").strip()
    if not webhook_url:
        if not backend_url:
            raise ValueError("Set BACKEND_TELEGRAM_WEBHOOK_URL, or BACKEND_URL to derive it")
        webhook_url = backend_url.rstrip("/") + WEBHOOK_PATH
    if not webhook_url.startswith("https://"):
        raise ValueError(f"The Telegram webhook URL must be HTTPS: {webhook_url}")

    return TelegramConfig(bot_token=bot_token, webhook_secret=webhook_secret, webhook_url=webhook_url)
