from typing import Optional

from app.i18n.types import Locale


class LocaleNotEnabledError(Exception):
    """
    Raised when voice input is not offered in the locale of the request.
    """

    def __init__(self, locale: Locale):
        super().__init__(f"Speech-to-text is not enabled for the locale {locale.value}")
        self.locale = locale


class EmptyTranscriptionError(Exception):
    """
    Raised when no speech was recognized in the recording.
    """


class SpeechToTextServiceError(Exception):
    """
    Raised when the recording could not be transcribed, because the external service failed.
    """


class SpeechToTextAdapterError(Exception):
    """
    Raised by an adapter when the external speech-to-text service fails.
    The message names the failure only: it never contains audio or a transcript.
    """

    def __init__(self, message: str, *, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        """ The HTTP status of the failure, if any. A transient one (e.g. 503) makes the call worth retrying. """
