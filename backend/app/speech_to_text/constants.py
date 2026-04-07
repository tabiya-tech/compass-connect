# Maximum audio file size: 10 MB
MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024

# Maximum multipart overhead for early Content-Length rejection
MAX_MULTIPART_OVERHEAD_BYTES = 1024

# Allowed MIME types from browser MediaRecorder and phone recordings
ALLOWED_AUDIO_MIME_TYPES = {
    "audio/webm",
    "audio/webm;codecs=opus",
    "audio/ogg",
    "audio/ogg;codecs=opus",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/x-m4a",
    "audio/aac",
    "video/mp4",
    "video/webm",
}

# Default language for transcription
DEFAULT_LANGUAGE_CODE = "en-US"
