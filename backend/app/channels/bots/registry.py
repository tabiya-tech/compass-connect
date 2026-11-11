from app.app_config import ApplicationConfig
from app.channels.bots.bot import ChannelBot


def build_channel_bots(app_config: ApplicationConfig) -> list[ChannelBot]:
    """
    Build the bots of the channels configured in the application config. A channel without settings has no bot.
    """
    bots: list[ChannelBot] = []

    if app_config.telegram_config is not None:
        # imported here: the backend loads the Telegram library only when the bot is on
        from app.channels.bots.telegram.bot import TelegramBot
        bots.append(TelegramBot(config=app_config.telegram_config,
                                default_locale=app_config.language_config.default_locale))

    return bots
