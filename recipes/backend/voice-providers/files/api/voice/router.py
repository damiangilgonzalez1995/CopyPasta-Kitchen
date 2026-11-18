"""POST /voice/transcribe (multipart `file`, optional `language`) -> {text, language}
POST /voice/synthesize {text, voice?} -> audio bytes (audio/mpeg...), `Cache-Control: no-store`.

Nothing is stored: not the audio, not the text. The upload is read in memory and cut as soon as it
passes the limit. `VoiceError` codes map to HTTP here and nowhere else:
    invalid_audio -> 415 (format) / 413 (size) / 422 (empty, too short)   no speech -> 422 {"code": "no_speech"}
    text_too_long -> 413   invalid_voice -> 422   rate_limited -> 429   timeout -> 504   unavailable -> 502 (503 if misconfigured)
"""

import re

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import BaseModel, Field

from ..auth import CurrentUser, get_current_user
from ..errors import ApiError
from voice import AudioInput, Synthesizer, Transcriber, VoiceError, VoiceErrorCode

router = APIRouter(prefix="/voice", tags=["voice"])

LANGUAGE = re.compile(r"^[a-z]{2}(-[A-Za-z]{2})?$")
READ_CHUNK = 64 * 1024


def get_transcriber(request: Request) -> Transcriber:
    transcriber: Transcriber | None = getattr(request.app.state, "transcriber", None)
    if transcriber is None:
        raise ApiError(503, "voice_unavailable")  # the app was built without voice
    return transcriber


def get_synthesizer(request: Request) -> Synthesizer:
    synthesizer: Synthesizer | None = getattr(request.app.state, "synthesizer", None)
    if synthesizer is None:
        raise ApiError(503, "voice_unavailable")
    return synthesizer


class TranscribeResponse(BaseModel):
    text: str
    language: str | None


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=1)
    voice: str | None = None


async def read_bounded(file: UploadFile, max_bytes: int) -> bytes:
    """Reads the upload in memory and stops as soon as it exceeds `max_bytes` (413), so a huge
    body never gets buffered whole."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(READ_CHUNK):
        total += len(chunk)
        if total > max_bytes:
            raise ApiError(413, "audio_too_large", max_bytes=max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    user: CurrentUser = Depends(get_current_user),
    transcriber: Transcriber = Depends(get_transcriber),
) -> TranscribeResponse:
    if language is not None and not LANGUAGE.match(language):
        raise ApiError(422, "invalid_language")
    mime = (file.content_type or "").split(";")[0].strip().lower()
    audio = AudioInput(content=await read_bounded(file, transcriber.max_bytes), mime=mime)
    if audio.extension is None:
        raise ApiError(415, "unsupported_audio_format", received=mime)
    if not audio.content:
        raise ApiError(422, "empty_audio")
    try:
        result = await transcriber.transcribe(audio, language=language)
    except VoiceError as error:
        raise _http_error(error) from None
    if not result.text:
        raise ApiError(422, "no_speech")
    return TranscribeResponse(text=result.text, language=result.language)


@router.post("/synthesize", response_class=Response)
async def synthesize(
    body: SynthesizeRequest,
    user: CurrentUser = Depends(get_current_user),
    synthesizer: Synthesizer = Depends(get_synthesizer),
) -> Response:
    try:
        speech = await synthesizer.synthesize(body.text, voice=body.voice)
    except VoiceError as error:
        raise _http_error(error) from None
    return Response(content=speech.audio, media_type=speech.mime, headers={"Cache-Control": "no-store"})


def _http_error(error: VoiceError) -> ApiError:
    match error.code:
        case VoiceErrorCode.INVALID_AUDIO:
            return ApiError(422, "invalid_audio")
        case VoiceErrorCode.EMPTY_TEXT:
            return ApiError(422, "empty_text")
        case VoiceErrorCode.TEXT_TOO_LONG:
            return ApiError(413, "text_too_long")
        case VoiceErrorCode.INVALID_VOICE:
            return ApiError(422, "invalid_voice")
        case VoiceErrorCode.RATE_LIMITED:
            return ApiError(429, "provider_rate_limited", headers={"Retry-After": "5"})
        case VoiceErrorCode.TIMEOUT:
            return ApiError(504, "provider_timeout")
    return ApiError(502 if error.retryable else 503, "provider_unavailable")
