# Maximum text length for synthesis
MAX_TEXT_LENGTH = 5000

# Default language for synthesis
DEFAULT_LANGUAGE_CODE = "en-US"

# Map application language codes to Google Cloud TTS voice names.
# Chirp 3 HD voices provide the most natural-sounding speech.
# For languages without a Chirp 3 HD voice, fall back to English.
LANGUAGE_TO_VOICE: dict[str, str] = {
    "en-US": "en-US-Chirp3-HD-Achernar",
    "en-GB": "en-GB-Chirp3-HD-Achernar",
    "ny-ZM": "en-US-Chirp3-HD-Achernar",  # Chichewa not supported; fall back to English
    "es-ES": "es-ES-Chirp3-HD-Achernar",
    "es-AR": "es-ES-Chirp3-HD-Achernar",
    "sw-KE": "sw-KE-Chirp3-HD-Achernar",
}

DEFAULT_VOICE_NAME = "en-US-Chirp3-HD-Achernar"
