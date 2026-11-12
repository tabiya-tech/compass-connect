from typing import Optional

import pytest

from app.channels.config import parse_channels_config
from app.channels.types import Channel

BACKEND_URL = "https://compass.test"
TOKEN = "123:abc"  # nosec B105 # a test value
SECRET = "s3cret"  # nosec B105 # a test value


def _parse(enable_channels: Optional[str], enable_telegram_bot: Optional[str], *, token: Optional[str] = TOKEN,
           secret: Optional[str] = SECRET, webhook_url: Optional[str] = None):
    return parse_channels_config(enable_channels=enable_channels, enable_telegram_bot=enable_telegram_bot,
                                 telegram_bot_token=token, telegram_webhook_secret=secret,
                                 telegram_webhook_url=webhook_url, backend_url=BACKEND_URL)


class TestParseChannelsConfig:
    @pytest.mark.parametrize("given_enable_channels", [None, "", "false", "no", "1"])
    def test_channels_are_off_unless_true(self, given_enable_channels: Optional[str]):
        # WHEN BACKEND_ENABLE_CHANNELS is not set, or not "true"
        actual = _parse(given_enable_channels, None)

        # THEN the channels routes are off, and no bot runs, even with the secrets of a bot set
        assert actual.enabled is False
        assert actual.enabled_bots == []

    @pytest.mark.parametrize("given_enable_telegram_bot", [None, "false"])
    def test_channels_api_without_the_bot(self, given_enable_telegram_bot: Optional[str]):
        # WHEN the channels are enabled, and not the Telegram bot
        actual = _parse("true", given_enable_telegram_bot, token=None, secret=None)

        # THEN the channels API is on, with no bot, and the bot needs no secrets
        assert actual.enabled is True
        assert actual.enabled_bots == []

    @pytest.mark.parametrize("given_value", ["true", "TRUE", " True "])
    def test_enables_the_telegram_bot(self, given_value: str):
        # WHEN the channels and the Telegram bot are enabled
        actual = _parse(given_value, given_value, webhook_url="https://tunnel.test/hook")

        # THEN the Telegram bot runs with its settings
        assert actual.enabled is True
        assert actual.enabled_bots == [Channel.TELEGRAM]
        assert actual.telegram.bot_token == TOKEN
        assert actual.telegram.webhook_secret == SECRET
        assert actual.telegram.webhook_url == "https://tunnel.test/hook"

    def test_rejects_the_telegram_bot_without_the_channels(self):
        # the bot needs the channels routes for its webhook
        with pytest.raises(ValueError):
            _parse(None, "true")

    def test_rejects_the_telegram_bot_without_its_token(self):
        with pytest.raises(ValueError):
            _parse("true", "true", token=None)
