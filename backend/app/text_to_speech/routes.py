import asyncio
import logging
from http import HTTPStatus

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from starlette.responses import Response

from app.app_config import get_application_config
from app.constants.errors import HTTPErrorResponse
from app.gateway.rate_limiter import ClientRateLimiter
from app.text_to_speech.adapter import GeminiTextToSpeechAdapter
from app.text_to_speech.errors import EmptySynthesisError, LocaleNotEnabledError, TextToSpeechServiceError
from app.text_to_speech.service import ITextToSpeechService, TextToSpeechService
from app.text_to_speech.types import SynthesizeRequest, TextToSpeechConfig
from app.users.auth import Authentication, UserInfo

logger = logging.getLogger(__name__)

_service_lock = asyncio.Lock()
_service_singleton: ITextToSpeechService | None = None
_rate_limiter_singleton: ClientRateLimiter | None = None


def get_text_to_speech_config() -> TextToSpeechConfig:
    return get_application_config().text_to_speech_config


async def get_text_to_speech_service(
        config: TextToSpeechConfig = Depends(get_text_to_speech_config)) -> ITextToSpeechService:
    global _service_singleton  # pylint: disable=global-statement
    if _service_singleton is None:
        async with _service_lock:
            if _service_singleton is None:
                adapter = GeminiTextToSpeechAdapter(model=config.model)
                _service_singleton = TextToSpeechService(config=config, adapter=adapter)
    return _service_singleton


def get_text_to_speech_rate_limiter(
        config: TextToSpeechConfig = Depends(get_text_to_speech_config)) -> ClientRateLimiter:
    global _rate_limiter_singleton  # pylint: disable=global-statement
    if _rate_limiter_singleton is None:
        _rate_limiter_singleton = ClientRateLimiter(config.rate_limit_per_minute)
    return _rate_limiter_singleton


def add_text_to_speech_routes(app: FastAPI, authentication: Authentication, config: TextToSpeechConfig) -> None:
    """
    Adds the read aloud routes, when read aloud is enabled for the deployment.
    Off, nothing is added: no route, and no Google client is ever built.
    """
    if not config.enabled:
        return
    router = APIRouter(prefix="/text-to-speech", tags=["text-to-speech"])

    @router.post(
        path="/synthesize",
        status_code=HTTPStatus.OK,
        response_class=Response,
        responses={
            HTTPStatus.OK: {"content": {"audio/mpeg": {"schema": {"type": "string", "format": "binary"}}}},
            HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse},
            HTTPStatus.UNPROCESSABLE_ENTITY: {"model": HTTPErrorResponse},
            HTTPStatus.TOO_MANY_REQUESTS: {"model": HTTPErrorResponse},
            HTTPStatus.BAD_GATEWAY: {"model": HTTPErrorResponse},
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        name="read a text aloud",
        description="Reads a plain text aloud in the voice of its locale. Returns the audio as MP3.",
    )
    async def _synthesize(
            body: SynthesizeRequest,
            user_info: UserInfo = Depends(authentication.get_user_info()),
            config: TextToSpeechConfig = Depends(get_text_to_speech_config),
            rate_limiter: ClientRateLimiter = Depends(get_text_to_speech_rate_limiter),
            service: ITextToSpeechService = Depends(get_text_to_speech_service),
    ) -> Response:
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="The text is empty")
        text_bytes = len(text.encode("utf-8"))
        if text_bytes > config.max_text_bytes:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST,
                                detail=f"The text is longer than {config.max_text_bytes} bytes")

        retry_after = rate_limiter.acquire(user_info.user_id)
        if retry_after is not None:
            logger.warning("Text-to-speech rate limit reached {user_id=%s}", user_info.user_id)
            raise HTTPException(status_code=HTTPStatus.TOO_MANY_REQUESTS,
                                detail="Too many requests, please try again later.",
                                headers={"Retry-After": str(retry_after)})

        logger.info("Synthesizing speech {user_id=%s, locale='%s', text_bytes=%s}", user_info.user_id,
                    body.locale.value, text_bytes)
        try:
            audio = await service.synthesize(text=text, locale=body.locale)
        except LocaleNotEnabledError as e:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST,
                                detail=f"Read aloud is not available in {body.locale.value}") from e
        except EmptySynthesisError as e:
            raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                                detail="No audio was produced for the text") from e
        except TextToSpeechServiceError as e:
            logger.error("Text-to-speech failed {user_id=%s, locale='%s'}", user_info.user_id, body.locale.value,
                         exc_info=True)
            raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY,
                                detail="The text-to-speech service is unavailable") from e
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Unexpected error while synthesizing speech {user_id=%s}", user_info.user_id)
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                                detail="Oops! Something went wrong.") from e

        return Response(content=audio.content, media_type=audio.media_type)

    app.include_router(router)
