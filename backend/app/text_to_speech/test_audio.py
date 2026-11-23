import io
import math
import struct
import wave

import pytest

from app.text_to_speech.audio import AudioConversionError, wav_to_mp3

_MPEG_FRAME_SYNC = 0xFFE0
""" The first 11 bits of an MPEG audio frame header. """


def make_wav(*, seconds: float = 0.5, sample_rate: int = 24_000, channels: int = 1, sample_width: int = 2) -> bytes:
    """ A tone, as a WAV file like the ones of Gemini TTS: 16-bit PCM, 24 kHz, mono by default. """
    frames = int(seconds * sample_rate)
    peak = 2 ** (8 * sample_width - 1) - 1
    sample_format = {1: "B", 2: "h"}[sample_width]
    samples = []
    for i in range(frames):
        value = int(peak * 0.5 * math.sin(2 * math.pi * 440 * i / sample_rate))
        samples.extend([value + (peak if sample_width == 1 else 0)] * channels)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack(f"<{len(samples)}{sample_format}", *samples))
    return buffer.getvalue()


def is_mp3(audio: bytes) -> bool:
    return audio[:3] == b"ID3" or (len(audio) > 1 and (audio[0] << 8 | audio[1]) & _MPEG_FRAME_SYNC == _MPEG_FRAME_SYNC)


class TestWavToMp3:
    @pytest.mark.parametrize("given_channels", [1, 2], ids=["mono, as Gemini TTS", "stereo"])
    def test_encodes_a_wav_file_of_16_bit_pcm_to_mp3(self, given_channels):
        # GIVEN a WAV file of 16-bit PCM at 24 kHz
        given_wav = make_wav(channels=given_channels)

        # WHEN it is encoded to MP3
        actual_mp3 = wav_to_mp3(given_wav)

        # THEN expect MP3 audio
        assert is_mp3(actual_mp3)
        # AND much smaller than the WAV file
        assert len(actual_mp3) < len(given_wav) / 4

    @pytest.mark.parametrize("given_audio", [
        b"",
        b"not a wav file",
        b"ID3\x04\x00\x00\x00\x00\x00\x00",
    ], ids=["empty", "not audio", "mp3, not wav"])
    def test_rejects_audio_that_is_not_a_wav_file(self, given_audio):
        # WHEN audio that is not a WAV file is encoded
        # THEN expect an AudioConversionError
        with pytest.raises(AudioConversionError):
            wav_to_mp3(given_audio)

    def test_rejects_a_wav_file_that_is_not_16_bit_pcm(self):
        # GIVEN a WAV file of 8-bit PCM
        given_wav = make_wav(sample_width=1)

        # WHEN it is encoded
        # THEN expect an AudioConversionError
        with pytest.raises(AudioConversionError, match="8-bit"):
            wav_to_mp3(given_wav)

    def test_rejects_a_wav_file_without_audio(self):
        # GIVEN a WAV file with a header but no frames
        given_wav = make_wav(seconds=0)

        # WHEN it is encoded
        # THEN expect an AudioConversionError
        with pytest.raises(AudioConversionError, match="no audio"):
            wav_to_mp3(given_wav)

    def test_rejects_a_wav_file_with_more_channels_than_mp3_takes(self):
        # GIVEN a WAV file with three channels
        given_wav = make_wav(channels=3)

        # WHEN it is encoded
        # THEN expect an AudioConversionError
        with pytest.raises(AudioConversionError):
            wav_to_mp3(given_wav)
