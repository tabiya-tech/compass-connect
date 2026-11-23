import pytest
from pydantic import ValidationError

from app.speech_to_text.types import ALLOWED_AUDIO_MIME_TYPES, AudioUpload, is_allowed_audio_mime_type

_GIVEN_CONTENT = b"recorded-audio"


class TestAudioUpload:
    @pytest.mark.parametrize("given_mime_type", sorted(ALLOWED_AUDIO_MIME_TYPES))
    def test_accepts_the_media_types_of_the_recordings_accepted(self, given_mime_type):
        # WHEN a recording of an accepted media type is made
        actual_audio = AudioUpload(content=_GIVEN_CONTENT, mime_type=given_mime_type)

        # THEN expect its media type
        assert actual_audio.mime_type == given_mime_type

    @pytest.mark.parametrize("given_mime_type", ["text/plain", "audio/webm;codecs=opus", "Audio/WebM", ""],
                             ids=["not audio", "with parameters", "not normalized", "empty"])
    def test_rejects_any_other_media_type(self, given_mime_type):
        # WHEN a recording of another media type is made
        # THEN expect a validation error that names the media type field
        with pytest.raises(ValidationError, match="mime_type"):
            AudioUpload(content=_GIVEN_CONTENT, mime_type=given_mime_type)


class TestIsAllowedAudioMimeType:
    @pytest.mark.parametrize("given_mime_type, expected_allowed", [
        *[(mime_type, True) for mime_type in sorted(ALLOWED_AUDIO_MIME_TYPES)],
        ("text/plain", False),
        ("audio/webm;codecs=opus", False),
    ])
    def test_tells_whether_a_media_type_is_accepted(self, given_mime_type, expected_allowed):
        # WHEN a media type is checked
        # THEN expect it to be accepted only if it is one of the recordings accepted
        assert is_allowed_audio_mime_type(given_mime_type) is expected_allowed
