"""
Smoke test of the Gemini TTS adapter against the real Vertex AI API, run by hand before a release:
    pytest -m smoke_test app/text_to_speech/test_gemini_smoke.py
Skipped without Google credentials (GOOGLE_APPLICATION_CREDENTIALS, or `gcloud auth application-default login`).
"""
import google.auth
import pytest
from google.auth.exceptions import DefaultCredentialsError

from app.text_to_speech.adapter import GeminiTextToSpeechAdapter
from app.text_to_speech.audio import wav_to_mp3
from app.text_to_speech.test_audio import is_mp3
from app.text_to_speech.types import VoiceSettings


def _has_google_credentials() -> bool:
    try:
        google.auth.default()
        return True
    except DefaultCredentialsError:
        return False


@pytest.mark.smoke_test
@pytest.mark.skipif(not _has_google_credentials(), reason="needs Google credentials")
@pytest.mark.asyncio
@pytest.mark.parametrize("given_model", ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"])
async def test_a_short_en_us_sentence_is_synthesized_to_wav_that_encodes_to_mp3(given_model):
    # GIVEN the Gemini TTS adapter for the model
    given_adapter = GeminiTextToSpeechAdapter(model=given_model)
    # AND the en-US voice of the default config
    given_voice = VoiceSettings(language_code="en-US", voice="Kore", style="warm, clear and friendly, at a moderate pace")

    # WHEN a short sentence is synthesized
    actual_wav = await given_adapter.synthesize(text="Let's talk about your work experience.", voice=given_voice)

    # THEN expect a WAV file
    expected_wav_header = b"RIFF"
    assert actual_wav[:4] == expected_wav_header
    # AND it to encode to MP3
    assert is_mp3(wav_to_mp3(actual_wav))
