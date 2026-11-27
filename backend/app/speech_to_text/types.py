from typing import Annotated, Literal, TypeGuard, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.i18n.types import Locale

MAX_RECORDING_SECONDS_LIMIT = 60
""" The synchronous Recognize method of Speech-to-Text v2 takes at most one minute of audio. """

MAX_AUDIO_BYTES_LIMIT = 10 * 1024 * 1024
""" The largest request the synchronous Recognize method accepts with inline audio: 10 MB. """

SpeechToTextModel = Literal["chirp_3"]
""" The Speech-to-Text models we support. """

_CONFIG_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, alias_generator=to_camel, populate_by_name=True)


class SpeechToTextConfig(BaseModel):
    """
    The voice input (speech-to-text) settings of the deployment. Off by default.
    Loaded from the BACKEND_SPEECH_TO_TEXT_CONFIG environment variable, see `parse_speech_to_text_config`.
    """
    model_config = _CONFIG_MODEL_CONFIG

    enabled: bool = False
    """ Whether voice input is on for the deployment. Off, the routes are not registered. """

    model: SpeechToTextModel = "chirp_3"
    """ The Speech-to-Text model. """

    max_recording_seconds: Annotated[int, Field(gt=0, le=MAX_RECORDING_SECONDS_LIMIT)] = MAX_RECORDING_SECONDS_LIMIT
    """ The longest recording, in seconds. The frontend stops recording when it is reached. """

    max_audio_bytes: Annotated[int, Field(gt=0, le=MAX_AUDIO_BYTES_LIMIT)] = MAX_AUDIO_BYTES_LIMIT
    """ The largest recording the backend accepts, in bytes. """

    rate_limit_per_minute: Annotated[int, Field(gt=0)] = 10
    """ How many recordings a user can transcribe per minute. One call per recording. """

    locales: frozenset[Locale] = frozenset()
    """
    The locales voice input is offered in. Chirp 3 transcribes each in its own language: the locale is the BCP-47
    language code, e.g. "sw-KE", unless it has a fallback locale.
    """

    fallback_locales: dict[Locale, Locale] = Field(default_factory=dict)
    """
    The locale whose language Chirp 3 hears, for a locale it does not support, e.g. {"es-AR": "es-ES"}.
    The locale stays the one of the user: only the language sent to Chirp 3 changes.
    """

    @model_validator(mode="after")
    def _an_enabled_feature_has_a_locale(self) -> "SpeechToTextConfig":
        if self.enabled and not self.locales:
            raise ValueError("speech-to-text is enabled, but has no locale")
        return self

    @model_validator(mode="after")
    def _a_fallback_is_for_an_offered_locale_and_another_one(self) -> "SpeechToTextConfig":
        for locale, fallback in self.fallback_locales.items():
            if locale not in self.locales:
                raise ValueError(f"fallbackLocales has {locale.value}, which is not one of the locales")
            if fallback == locale:
                raise ValueError(f"fallbackLocales has {locale.value} falling back to itself")
        return self

    @property
    def enabled_locales(self) -> frozenset[Locale]:
        """ The locales voice input is offered in. Empty when the feature is off. """
        return self.locales if self.enabled else frozenset()

    def is_locale_enabled(self, locale: Locale) -> bool:
        """ Whether voice input is offered in the locale. """
        return locale in self.enabled_locales

    def language_code(self, locale: Locale) -> str:
        """ The language Chirp 3 hears in the locale, as a BCP-47 code: that of its fallback locale, if it has one. """
        return self.fallback_locales.get(locale, locale).value

AudioMimeType = Literal[
    "audio/webm",  # Chrome, Firefox and Edge record Opus in WebM
    "audio/mp4",  # Safari records AAC in MP4
    "audio/ogg",  # Opus in Ogg, for a browser that records neither of the above
]
"""
The media types of the recordings accepted, without their parameters: the compressed formats the browser records in
(see PREFERRED_MIME_TYPES in the frontend's useSpeechToText). Chirp 3 detects their encoding itself.
"""

ALLOWED_AUDIO_MIME_TYPES: frozenset[str] = frozenset(get_args(AudioMimeType))
""" The values of AudioMimeType, to check a media type received. """


def is_allowed_audio_mime_type(mime_type: str) -> TypeGuard[AudioMimeType]:
    """ Whether a media type, without its parameters, is one of the recordings accepted. """
    return mime_type in ALLOWED_AUDIO_MIME_TYPES


class AudioUpload(BaseModel):
    """
    A recording to transcribe, as the browser uploaded it.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: bytes = Field(min_length=1)
    """ The encoded audio. """

    mime_type: AudioMimeType
    """ The media type of the recording, without its parameters, e.g. "audio/webm". """


class Transcription(BaseModel):
    """
    The text of a recording.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    """ The transcript, trimmed. Never empty: an empty result is an EmptyTranscriptionError. """

    locale: Locale
    """ The locale the recording was transcribed in. """


class TranscriptionResponse(BaseModel):
    """
    The response of POST /speech-to-text/transcribe.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(description="The transcript of the recording.")
    """ The transcript of the recording. """

    locale: Locale = Field(description="The locale the recording was transcribed in.")
    """ The locale the recording was transcribed in. """
