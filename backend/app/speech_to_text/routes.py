import asyncio
import logging
from http import HTTPStatus

import google.auth
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile

from app.app_config import get_application_config
from app.constants.errors import HTTPErrorResponse
from app.gateway.rate_limiter import ClientRateLimiter
from app.i18n.types import Locale
from app.speech_to_text.adapter import ChirpSpeechToTextAdapter
from app.speech_to_text.errors import EmptyTranscriptionError, LocaleNotEnabledError, SpeechToTextServiceError
from app.speech_to_text.service import ISpeechToTextService, SpeechToTextService
from app.speech_to_text.types import (AudioUpload, SpeechToTextConfig, TranscriptionResponse,
                                      is_allowed_audio_mime_type)
from app.users.auth import Authentication, UserInfo

logger = logging.getLogger(__name__)

MAX_MULTIPART_OVERHEAD_BYTES = 64 * 1024
""" Room for the multipart boundaries and the locale field in the early check of the Content-Length header. """

_service_lock = asyncio.Lock()
_service_singleton: ISpeechToTextService | None = None
_rate_limiter_singleton: ClientRateLimiter | None = None


def get_speech_to_text_config() -> SpeechToTextConfig:
    return get_application_config().speech_to_text_config


def _get_default_project_id() -> str:
    _, project_id = google.auth.default()
    if not project_id:
        raise RuntimeError("No Google Cloud project is set for speech-to-text, set GOOGLE_CLOUD_PROJECT")
    return project_id


async def get_speech_to_text_service(
        config: SpeechToTextConfig = Depends(get_speech_to_text_config)) -> ISpeechToTextService:
    global _service_singleton  # pylint: disable=global-statement
    if _service_singleton is None:
        async with _service_lock:
            if _service_singleton is None:
                adapter = ChirpSpeechToTextAdapter(project_id=_get_default_project_id(), model=config.model)
                _service_singleton = SpeechToTextService(config=config, adapter=adapter)
    return _service_singleton


def get_speech_to_text_rate_limiter(
        config: SpeechToTextConfig = Depends(get_speech_to_text_config)) -> ClientRateLimiter:
    global _rate_limiter_singleton  # pylint: disable=global-statement
    if _rate_limiter_singleton is None:
        _rate_limiter_singleton = ClientRateLimiter(config.rate_limit_per_minute)
    return _rate_limiter_singleton


def _normalize_mime_type(content_type: str | None) -> str:
    """ The media type without its parameters, e.g. "Audio/WebM ; codecs=opus" -> "audio/webm". """
    return (content_type or "").split(";", 1)[0].strip().lower()


def _check_content_length(request: Request, max_audio_bytes: int) -> None:
    """ Refuses an oversized upload from its Content-Length header, before reading the body. """
    try:
        content_length = int(request.headers.get("content-length", ""))
    except ValueError:
        return
    if content_length > max_audio_bytes + MAX_MULTIPART_OVERHEAD_BYTES:
        logger.warning("Audio upload refused from its header {content_length=%s, max_audio_bytes=%s}",
                       content_length, max_audio_bytes)
        raise HTTPException(status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE, detail="The recording is too large")


def add_speech_to_text_routes(app: FastAPI, authentication: Authentication, config: SpeechToTextConfig) -> None:
    """
    Adds the voice input routes, when voice input is enabled for the deployment.
    Off, nothing is added: no route, and no Google client is ever built.
    """
    if not config.enabled:
        return
    router = APIRouter(prefix="/speech-to-text", tags=["speech-to-text"])

    @router.post(
        path="/transcribe",
        status_code=HTTPStatus.OK,
        response_model=TranscriptionResponse,
        responses={
            HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse},
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE: {"model": HTTPErrorResponse},
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE: {"model": HTTPErrorResponse},
            HTTPStatus.UNPROCESSABLE_ENTITY: {"model": HTTPErrorResponse},
            HTTPStatus.TOO_MANY_REQUESTS: {"model": HTTPErrorResponse},
            HTTPStatus.BAD_GATEWAY: {"model": HTTPErrorResponse},
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        name="transcribe a recording",
        description="Transcribes a recording of the user, made in the browser, in the language of its locale.",
    )
    async def _transcribe(
            request: Request,
            audio: UploadFile = File(description="The recording, e.g. audio/webm or audio/mp4."),
            locale: Locale = Form(description="The locale the user speaks in, e.g. en-US."),
            user_info: UserInfo = Depends(authentication.get_user_info()),
            speech_config: SpeechToTextConfig = Depends(get_speech_to_text_config),
            rate_limiter: ClientRateLimiter = Depends(get_speech_to_text_rate_limiter),
            service: ISpeechToTextService = Depends(get_speech_to_text_service),
    ) -> TranscriptionResponse:
        _check_content_length(request, speech_config.max_audio_bytes)

        mime_type = _normalize_mime_type(audio.content_type)
        if not is_allowed_audio_mime_type(mime_type):
            raise HTTPException(status_code=HTTPStatus.UNSUPPORTED_MEDIA_TYPE, detail="Unsupported audio format")

        content = await audio.read(speech_config.max_audio_bytes + 1)
        if len(content) > speech_config.max_audio_bytes:
            raise HTTPException(status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE, detail="The recording is too large")
        if not content:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="The recording is empty")

        retry_after = rate_limiter.acquire(user_info.user_id)
        if retry_after is not None:
            logger.warning("Speech-to-text rate limit reached {user_id=%s}", user_info.user_id)
            raise HTTPException(status_code=HTTPStatus.TOO_MANY_REQUESTS,
                                detail="Too many requests, please try again later.",
                                headers={"Retry-After": str(retry_after)})

        logger.info("Transcribing audio {user_id=%s, locale='%s', audio_bytes=%s, mime_type='%s'}",
                    user_info.user_id, locale.value, len(content), mime_type)
        try:
            transcription = await service.transcribe(audio=AudioUpload(content=content, mime_type=mime_type),
                                                     locale=locale)
        except LocaleNotEnabledError as e:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST,
                                detail=f"Voice input is not available in {locale.value}") from e
        except EmptyTranscriptionError as e:
            raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                                detail="No speech was recognized in the recording") from e
        except SpeechToTextServiceError as e:
            logger.error("Speech-to-text failed {user_id=%s, locale='%s'}", user_info.user_id, locale.value,
                         exc_info=True)
            raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY,
                                detail="The speech-to-text service is unavailable") from e
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Unexpected error while transcribing audio {user_id=%s}", user_info.user_id)
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                                detail="Oops! Something went wrong.") from e

        return TranscriptionResponse(text=transcription.text, locale=transcription.locale)

    app.include_router(router)
