from typing import Optional

import pytest

from app.channels.bots.telegram.config import TelegramConfig, parse_telegram_config

BACKEND_URL = "https://compass.test/api"
TOKEN = "123:abc"  # nosec B105 # a test value
SECRET = "s3cret_-"  # nosec B105 # a test value


class TestParseTelegramConfig:
    def test_telegram_is_off_without_a_token(self):
        assert parse_telegram_config(bot_token=None, webhook_secret=SECRET, webhook_url=None,
                                     backend_url=BACKEND_URL) is None

    def test_derives_the_webhook_url_from_the_backend_url(self):
        # WHEN the config is parsed from a token and a secret
        actual = parse_telegram_config(bot_token=TOKEN, webhook_secret=SECRET, webhook_url=None,
                                       backend_url=BACKEND_URL + "/")

        # THEN the webhook is under the backend URL
        assert actual == TelegramConfig(bot_token=TOKEN, webhook_secret=SECRET,
                                        webhook_url="https://compass.test/api/api/channels/telegram/webhook")

    def test_uses_the_webhook_url_set(self):
        # WHEN the config is parsed with a webhook URL, e.g. a tunnel to a local backend
        actual = parse_telegram_config(bot_token=TOKEN, webhook_secret=SECRET,
                                       webhook_url="https://tunnel.test/api/channels/telegram/webhook",
                                       backend_url="http://localhost:8080")

        # THEN that URL is used
        assert actual.webhook_url == "https://tunnel.test/api/channels/telegram/webhook"

    @pytest.mark.parametrize("webhook_secret, webhook_url, backend_url", [
        pytest.param(None, None, BACKEND_URL, id="no secret"),
        pytest.param("not ok!", None, BACKEND_URL, id="secret with characters Telegram refuses"),
        pytest.param("s", None, "http://localhost:8080", id="webhook not https"),
        pytest.param("s", None, None, id="no webhook url and no backend url"),
    ])
    def test_rejects_invalid_settings(self, webhook_secret: Optional[str], webhook_url: Optional[str],
                                      backend_url: Optional[str]):
        with pytest.raises(ValueError):
            parse_telegram_config(bot_token=TOKEN, webhook_secret=webhook_secret, webhook_url=webhook_url,
                                  backend_url=backend_url)
