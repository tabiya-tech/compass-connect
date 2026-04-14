class TranscriptionError(Exception):
    """Base exception for speech-to-text transcription errors."""


class EmptyTranscriptionError(TranscriptionError):
    """Raised when Google STT returns no transcription results."""
    def __init__(self):
        super().__init__("No transcription results returned for the provided audio")


class SpeechToTextServiceError(TranscriptionError):
    """Raised when the Google Cloud STT API call fails."""
    def __init__(self, detail: str):
        super().__init__(f"Speech-to-text service error: {detail}")
        self.detail = detail
