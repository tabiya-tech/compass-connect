"""
Encodes the WAV audio of Gemini TTS to MP3, the format read aloud returns: Gemini 3.8 TTS cannot produce MP3, and MP3
is about a tenth of the size of WAV, which matters on mobile data.

The MP3 encoder is LAME, through lameenc (LGPL-3.0, used unmodified as a library).
"""
import io
import wave

import lameenc

MP3_BIT_RATE_KBPS = 64
""" Plenty for speech: Gemini TTS speaks at 24 kHz, mono. """

_MP3_QUALITY = 2
""" The quality of the encoder, from 2 (best) to 7 (fastest). The audio is short, so the best quality is affordable. """

_SAMPLE_WIDTH_BYTES = 2
""" The encoder takes 16-bit PCM, which is what Gemini TTS returns. """


class AudioConversionError(Exception):
    """
    Raised when the audio cannot be encoded to MP3, e.g. it is not a WAV file of 16-bit PCM.
    """


def wav_to_mp3(wav: bytes) -> bytes:
    """
    Encodes a WAV file of 16-bit PCM to MP3, keeping its sample rate and channels.

    :param wav: the WAV file, with its RIFF header
    :return: the MP3 audio
    :raises AudioConversionError: if the audio is not a WAV file of 16-bit PCM
    """
    try:
        with wave.open(io.BytesIO(wav), "rb") as wav_file:
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            pcm = wav_file.readframes(wav_file.getnframes())
    except (wave.Error, EOFError) as e:
        raise AudioConversionError(f"The audio is not a WAV file: {e}") from e

    if sample_width != _SAMPLE_WIDTH_BYTES:
        raise AudioConversionError(f"The WAV file has {sample_width * 8}-bit samples, not 16-bit")
    if not pcm:
        raise AudioConversionError("The WAV file has no audio")

    try:
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(MP3_BIT_RATE_KBPS)
        encoder.set_in_sample_rate(sample_rate)
        encoder.set_channels(channels)
        encoder.set_quality(_MP3_QUALITY)
        return bytes(encoder.encode(pcm) + encoder.flush())
    except RuntimeError as e:
        # lameenc raises RuntimeError for settings LAME does not take, e.g. more than two channels
        raise AudioConversionError(f"The audio cannot be encoded to MP3: {e}") from e
