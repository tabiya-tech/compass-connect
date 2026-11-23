"""
Smoke test of the Chirp adapter against the real Speech-to-Text API, run by hand before a release:
    pytest -m smoke_test app/speech_to_text/test_chirp_smoke.py
Skipped without Google credentials and a project (GOOGLE_APPLICATION_CREDENTIALS or
`gcloud auth application-default login`, and GOOGLE_CLOUD_PROJECT).
"""
from pathlib import Path

import google.auth
import pytest
from google.auth.exceptions import DefaultCredentialsError

from app.speech_to_text.adapter import ChirpSpeechToTextAdapter
from app.speech_to_text.types import AudioUpload

_FIXTURES = Path(__file__).parent / "test_fixtures"


def _google_project_id() -> str | None:
    try:
        _, project_id = google.auth.default()
        return project_id
    except DefaultCredentialsError:
        return None


@pytest.mark.smoke_test
@pytest.mark.skipif(_google_project_id() is None, reason="needs Google credentials and a project")
@pytest.mark.asyncio
@pytest.mark.parametrize("given_file, given_mime_type", [
    ("en-US-carpenter.webm", "audio/webm"),
    ("en-US-carpenter.mp4", "audio/mp4"),
], ids=["webm/opus", "mp4/aac"])
async def test_a_real_en_us_recording_is_transcribed_to_the_spoken_words(given_file, given_mime_type):
    # GIVEN the Chirp adapter, as the default config sets it up
    given_adapter = ChirpSpeechToTextAdapter(project_id=_google_project_id(), model="chirp_3")
    # AND a recording of "I worked as a carpenter for three years."
    given_audio = AudioUpload(content=(_FIXTURES / given_file).read_bytes(), mime_type=given_mime_type)
    # AND the words spoken in it, the number as Chirp may write it
    given_spoken_job = "carpenter"
    given_spoken_durations = ("three years", "3 years")

    # WHEN it is recognized in en-US
    actual_transcript = await given_adapter.recognize(audio=given_audio, language_code="en-US")

    # THEN expect the spoken words
    assert given_spoken_job in actual_transcript.lower()
    assert any(duration in actual_transcript.lower() for duration in given_spoken_durations)
