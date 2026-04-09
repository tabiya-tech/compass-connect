import asyncio
import logging
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import Response

from app.constants.errors import HTTPErrorResponse
from app.text_to_speech.constants import MAX_TEXT_LENGTH
from app.text_to_speech.errors import EmptySynthesisError, TextToSpeechServiceError
from app.text_to_speech.service import GoogleTextToSpeechService, ITextToSpeechService
from app.text_to_speech.types import SynthesizeRequest
from app.users.auth import Authentication, UserInfo

logger = logging.getLogger(__name__)

_tts_service_lock = asyncio.Lock()
_tts_service_singleton: ITextToSpeechService | None = None


async def _get_text_to_speech_service() -> ITextToSpeechService:
    global _tts_service_singleton  # pylint: disable=global-statement
    if _tts_service_singleton is None:
        async with _tts_service_lock:
            if _tts_service_singleton is None:
                _tts_service_singleton = GoogleTextToSpeechService()
    return _tts_service_singleton


# Public alias for dependency override in tests
get_text_to_speech_service = _get_text_to_speech_service


def add_text_to_speech_routes(app, authentication: Authentication):
    """Register text-to-speech routes on the given FastAPI app."""
    router = APIRouter(prefix="/text-to-speech", tags=["text-to-speech"])

    @router.post(
        path="/synthesize",
        status_code=HTTPStatus.OK,
        responses={
            HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse},
            HTTPStatus.UNPROCESSABLE_ENTITY: {"model": HTTPErrorResponse},
            HTTPStatus.BAD_GATEWAY: {"model": HTTPErrorResponse},
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        name="synthesize speech",
        description="Synthesize text into speech using Google Cloud Text-to-Speech.",
    )
    async def _synthesize_speech(
        body: SynthesizeRequest,
        user_info: UserInfo = Depends(authentication.get_user_info()),
        service: ITextToSpeechService = Depends(get_text_to_speech_service),
    ) -> Response:
        # Validate empty text
        if not body.text or not body.text.strip():
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Text is empty",
            )

        # Validate text length
        if len(body.text) > MAX_TEXT_LENGTH:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"Text length {len(body.text)} exceeds maximum allowed length of {MAX_TEXT_LENGTH}",
            )

        logger.info(
            "Synthesizing speech {user_id=%s, text_length=%s, language='%s'}",
            user_info.user_id,
            len(body.text),
            body.language,
        )

        try:
            audio_bytes = await service.synthesize(text=body.text, language_code=body.language)
            return Response(content=audio_bytes, media_type="audio/mpeg")
        except EmptySynthesisError as exc:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail="No audio content returned for the provided text",
            ) from exc
        except TextToSpeechServiceError as e:
            logger.error("Text-to-speech service error", exc_info=True)
            raise HTTPException(
                status_code=HTTPStatus.BAD_GATEWAY,
                detail="Upstream synthesis service unavailable",
            ) from e
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Unexpected error during synthesis")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred during synthesis",
            ) from e

    app.include_router(router)
