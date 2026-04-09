from pydantic import BaseModel, ConfigDict, Field


class SynthesizeRequest(BaseModel):
    """Request body for text-to-speech synthesis."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="The text to synthesize into speech")
    language: str = Field(default="en-US", description="The BCP-47 language code")
