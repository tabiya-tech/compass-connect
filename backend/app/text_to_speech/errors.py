class TextToSpeechError(Exception):
    """Base exception for text-to-speech synthesis errors."""


class EmptySynthesisError(TextToSpeechError):
    """Raised when Google TTS returns no audio content."""
    def __init__(self):
        super().__init__("No audio content returned for the provided text")


class TextToSpeechServiceError(TextToSpeechError):
    """Raised when the Google Cloud TTS API call fails."""
    def __init__(self, detail: str):
        super().__init__(f"Text-to-speech service error: {detail}")
        self.detail = detail
