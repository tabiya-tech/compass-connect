from pydantic import BaseModel, Field


class TranscriptionResponse(BaseModel):
    """Response returned after successful speech-to-text transcription."""

    class Config:
        """Pydantic model configuration."""
        extra = "forbid"

    text: str = Field(description="The transcribed text from the audio input")
    language_code: str = Field(description="The language code used for transcription")
