from app.app_config import ApplicationConfig
from app.channels.bots.bot import ChannelBot


def build_channel_bots(app_config: ApplicationConfig) -> list[ChannelBot]:
    """
    Build the bots the deployment enables (BACKEND_ENABLE_TELEGRAM_BOT). None when the channels are off.
    """
    channels_config = app_config.channels_config
    bots: list[ChannelBot] = []
    if not channels_config.enabled:
        return bots

    if channels_config.telegram is not None:
        # imported here: the backend loads the Telegram library only when the bot is on
        from app.channels.bots.telegram.bot import TelegramBot
        bots.append(TelegramBot(config=channels_config.telegram,
                                default_locale=app_config.language_config.default_locale))

    return bots
