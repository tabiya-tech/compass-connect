from typing import Annotated, Literal

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
    language code, e.g. "sw-KE".
    """

    @model_validator(mode="after")
    def _an_enabled_feature_has_a_locale(self) -> "SpeechToTextConfig":
        if self.enabled and not self.locales:
            raise ValueError("speech-to-text is enabled, but has no locale")
        return self

    @property
    def enabled_locales(self) -> frozenset[Locale]:
        """ The locales voice input is offered in. Empty when the feature is off. """
        return self.locales if self.enabled else frozenset()

    def is_locale_enabled(self, locale: Locale) -> bool:
        """ Whether voice input is offered in the locale. """
        return locale in self.enabled_locales
