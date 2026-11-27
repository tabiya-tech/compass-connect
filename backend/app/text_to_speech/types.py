from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

from app.i18n.types import Locale

MAX_INPUT_TOKENS = 8192
"""
The input limit of the Gemini 3.8 TTS models, in tokens. The text and the style of a request count towards it.
A token covers at least one byte of UTF-8, so a request of at most this many bytes stays within it.
"""

MAX_STYLE_BYTES = 1024
""" The longest speaking style, in bytes of UTF-8. Kept short, to leave the rest of the input limit to the text. """

MAX_TEXT_BYTES_LIMIT = MAX_INPUT_TOKENS - MAX_STYLE_BYTES

MIN_TEXT_BYTES = 4
""" The shortest text limit: the longest UTF-8 character, so a part of a split text always fits. """
""" The longest text read in one request, in bytes of UTF-8: what the longest style leaves of the input limit. """

TextToSpeechModel = Literal["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]
""" The Gemini 3.8 TTS models we support: the flash model, or the lite one for lower latency and cost. """


def _at_most_max_style_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_STYLE_BYTES:
        raise ValueError(f"must be at most {MAX_STYLE_BYTES} bytes in UTF-8")
    return value


VoiceName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
""" The name of a Gemini TTS voice, e.g. "Kore". """

SpeakingStyle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1),
                          AfterValidator(_at_most_max_style_bytes)]
""" How the text is spoken, e.g. "warm, clear and friendly, at a moderate pace". Sent apart from the text. """

_CONFIG_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, alias_generator=to_camel, populate_by_name=True)


class TextToSpeechLocaleConfig(BaseModel):
    """
    The read aloud settings of one locale.
    """
    model_config = _CONFIG_MODEL_CONFIG

    enabled: bool = False
    """
    Whether read aloud is offered in this locale. Gemini TTS speaks its language: the locale is the BCP-47 code, unless
    it has a fallback locale.
    """

    voice: VoiceName
    """ The voice that reads the messages of this locale. """

    style: SpeakingStyle
    """ The speaking style for this locale. """


class TextToSpeechConfig(BaseModel):
    """
    The read aloud (text-to-speech) settings of the deployment. Off by default.
    Loaded from the BACKEND_TEXT_TO_SPEECH_CONFIG environment variable, see `parse_text_to_speech_config`.
    """
    model_config = _CONFIG_MODEL_CONFIG

    enabled: bool = False
    """ Whether read aloud is on for the deployment. Off, the routes are not registered. """

    model: TextToSpeechModel = "gemini-3.8-flash-tts"
    """ The Gemini TTS model. """

    max_text_bytes: Annotated[int, Field(ge=MIN_TEXT_BYTES, le=MAX_TEXT_BYTES_LIMIT)] = MAX_TEXT_BYTES_LIMIT
    """
    The longest text read in one request, in bytes of UTF-8 (a Ge'ez character, as in Amharic, takes 3). The frontend
    splits longer messages into parts that fit.
    """

    rate_limit_per_minute: Annotated[int, Field(gt=0)] = 20
    """ How many texts a user can have read per minute. """

    locales: dict[Locale, TextToSpeechLocaleConfig] = Field(default_factory=dict)
    """ The settings per locale. A locale that is missing, or not enabled, has no read aloud. """

    fallback_locales: dict[Locale, Locale] = Field(default_factory=dict)
    """
    The locale whose language Gemini TTS speaks, for a locale it does not support, e.g. {"es-AR": "es-ES"}.
    The voice and the style stay those of the locale: only the language sent to Gemini TTS changes.
    """

    @model_validator(mode="after")
    def _an_enabled_feature_has_an_enabled_locale(self) -> "TextToSpeechConfig":
        if self.enabled and not any(settings.enabled for settings in self.locales.values()):
            raise ValueError("text-to-speech is enabled, but none of its locales is enabled")
        return self

    @model_validator(mode="after")
    def _a_fallback_is_for_a_configured_locale_and_another_one(self) -> "TextToSpeechConfig":
        for locale, fallback in self.fallback_locales.items():
            if locale not in self.locales:
                raise ValueError(f"fallbackLocales has {locale.value}, which is not one of the locales")
            if fallback == locale:
                raise ValueError(f"fallbackLocales has {locale.value} falling back to itself")
        return self

    @property
    def enabled_locales(self) -> frozenset[Locale]:
        """ The locales read aloud is offered in. Empty when the feature is off. """
        if not self.enabled:
            return frozenset()
        return frozenset(locale for locale, settings in self.locales.items() if settings.enabled)

    def locale_settings(self, locale: Locale) -> TextToSpeechLocaleConfig | None:
        """
        :return: the settings of the locale, or None if read aloud is not offered in it.
        """
        if not self.enabled:
            return None
        settings = self.locales.get(locale)
        return settings if settings is not None and settings.enabled else None

    def language_code(self, locale: Locale) -> str:
        """ The language Gemini TTS speaks in the locale, as a BCP-47 code: that of its fallback locale, if any. """
        return self.fallback_locales.get(locale, locale).value


SynthesisText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
""" The plain text to read aloud, trimmed. Markdown is stripped by the frontend before it is sent. """


class SynthesizeRequest(BaseModel):
    """
    The body of POST /text-to-speech/synthesize.
    The text is checked by the route (empty, too long) rather than here, so that it answers 400, not 422.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(description="The plain text to read aloud.")
    """ The plain text to read aloud. """

    locale: Locale = Field(description="The locale of the text, e.g. en-US.")
    """ The locale of the text. It selects the language and the voice. """


class VoiceSettings(BaseModel):
    """
    How a text is spoken, resolved by the service from the settings of a locale.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    language_code: str
    """ The language Gemini TTS speaks, as a BCP-47 code, e.g. "en-US". """

    voice: VoiceName
    """ The voice that reads the text. """

    style: SpeakingStyle
    """ The speaking style. """


class SynthesizedAudio(BaseModel):
    """
    The audio of a text read aloud.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: bytes
    """ The encoded audio. Never empty: no audio is an EmptySynthesisError. """

    media_type: Literal["audio/mpeg"]
    """ The media type of the content. """

    locale: Locale
    """ The locale the text was read in. """
