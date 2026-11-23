from typing import Optional

from app.i18n.types import Locale


class LocaleNotEnabledError(Exception):
    """
    Raised when read aloud is not offered in the locale of the request.
    """

    def __init__(self, locale: Locale):
        super().__init__(f"Text-to-speech is not enabled for the locale {locale.value}")
        self.locale = locale


class EmptySynthesisError(Exception):
    """
    Raised when the text-to-speech service returned no audio.
    """


class TextToSpeechServiceError(Exception):
    """
    Raised when the text could not be read aloud, because the external service failed.
    """


class TextToSpeechAdapterError(Exception):
    """
    Raised by an adapter when the external text-to-speech service fails.
    The message names the failure only: it never contains the text.
    """

    def __init__(self, message: str, *, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        """ The HTTP status of the failure, if any. A transient one (e.g. 503) makes the call worth retrying. """
