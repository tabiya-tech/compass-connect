import asyncio
import logging
from http import HTTPStatus

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.constants.errors import HTTPErrorResponse
from app.speech_to_text.constants import (
    ALLOWED_AUDIO_MIME_TYPES,
    DEFAULT_LANGUAGE_CODE,
    MAX_AUDIO_SIZE_BYTES,
    MAX_MULTIPART_OVERHEAD_BYTES,
)
from app.speech_to_text.errors import EmptyTranscriptionError, SpeechToTextServiceError
from app.speech_to_text.service import GoogleSpeechToTextService, ISpeechToTextService
from app.speech_to_text.types import TranscriptionResponse
from app.users.auth import Authentication, UserInfo

logger = logging.getLogger(__name__)

_stt_service_lock = asyncio.Lock()
_stt_service_singleton: ISpeechToTextService | None = None


async def _get_speech_to_text_service() -> ISpeechToTextService:
    global _stt_service_singleton  # pylint: disable=global-statement
    if _stt_service_singleton is None:
        async with _stt_service_lock:
            if _stt_service_singleton is None:
                _stt_service_singleton = GoogleSpeechToTextService()
    return _stt_service_singleton


# Public alias for dependency override in tests
get_speech_to_text_service = _get_speech_to_text_service


def _validate_request_size_header(request: Request):
    """Validate Content-Length before reading the body to fail fast on oversized uploads."""
    content_length_header = request.headers.get("content-length")
    if content_length_header is None:
        return
    try:
        content_length = int(content_length_header)
    except ValueError:
        return
    if content_length > (MAX_AUDIO_SIZE_BYTES + MAX_MULTIPART_OVERHEAD_BYTES):
        logger.warning(
            "413 via header-check: content_length=%s limit=%s",
            content_length,
            MAX_AUDIO_SIZE_BYTES,
        )
        raise HTTPException(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file exceeds maximum allowed size",
        )


def add_speech_to_text_routes(app, authentication: Authentication):
    """Register speech-to-text routes on the given FastAPI app."""
    router = APIRouter(prefix="/speech-to-text", tags=["speech-to-text"])

    @router.post(
        path="/transcribe",
        status_code=HTTPStatus.OK,
        response_model=TranscriptionResponse,
        responses={
            HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse},
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE: {"model": HTTPErrorResponse},
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE: {"model": HTTPErrorResponse},
            HTTPStatus.UNPROCESSABLE_ENTITY: {"model": HTTPErrorResponse},
            HTTPStatus.BAD_GATEWAY: {"model": HTTPErrorResponse},
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        name="transcribe audio",
        description="Transcribe audio input to text using Google Cloud Speech-to-Text.",
    )
    async def _transcribe_audio(
        request: Request,
        audio: UploadFile = File(..., description="Audio file recorded in the browser"),
        language: str = Form(default=DEFAULT_LANGUAGE_CODE),
        user_info: UserInfo = Depends(authentication.get_user_info()),
        service: ISpeechToTextService = Depends(get_speech_to_text_service),
    ) -> TranscriptionResponse:
        # Validate size early via Content-Length header
        _validate_request_size_header(request)

        # Validate MIME type — normalize by stripping spaces around semicolons
        raw_content_type = (audio.content_type or "").strip()
        # Check both the base type (e.g. "audio/webm") and the full type with params normalized
        # (e.g. "audio/webm;codecs=opus") to handle browsers that add spaces after ";"
        content_type = raw_content_type.split(";")[0].strip()
        normalized_content_type = ";".join(part.strip() for part in raw_content_type.split(";"))
        if content_type not in ALLOWED_AUDIO_MIME_TYPES and normalized_content_type not in ALLOWED_AUDIO_MIME_TYPES:
            raise HTTPException(
                status_code=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported audio format",
            )

        # Read and validate file size
        audio_bytes = await audio.read()
        if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
            raise HTTPException(
                status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                detail="Audio file exceeds maximum allowed size",
            )

        if len(audio_bytes) == 0:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Audio file is empty",
            )

        logger.info(
            "Transcribing audio {user_id=%s, size_bytes=%s, content_type='%s', language='%s'}",
            user_info.user_id,
            len(audio_bytes),
            audio.content_type,
            language,
        )

        try:
            return await service.transcribe(audio_bytes=audio_bytes, language_code=language)
        except EmptyTranscriptionError as exc:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail="No transcription results returned for the provided audio",
            ) from exc
        except SpeechToTextServiceError as e:
            logger.error("Speech-to-text service error", exc_info=True)
            raise HTTPException(
                status_code=HTTPStatus.BAD_GATEWAY,
                detail="Upstream transcription service unavailable",
            ) from e
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Unexpected error during transcription")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred during transcription",
            ) from e

    app.include_router(router)
