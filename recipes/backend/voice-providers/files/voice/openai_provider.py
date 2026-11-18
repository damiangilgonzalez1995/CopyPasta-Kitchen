"""OpenAI audio: `audio.transcriptions.create` (whisper-1, gpt-4o-transcribe, gpt-4o-mini-transcribe)
and `audio.speech.create` (gpt-4o-mini-tts, tts-1, tts-1-hd). One `AsyncOpenAI` client with
`max_retries=0` (the caller decides on retries) shared by both; `http_client=` is the test seam.
"""

import logging
from collections.abc import Iterable
from typing import Any

from pydantic import SecretStr

from .base import Synthesizer, Transcriber
from .models import AudioInput, VoiceError, VoiceErrorCode

logger = logging.getLogger(__name__)

OPENAI_VOICES = frozenset({"alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"})
SPEECH_MIME = {"mp3": "audio/mpeg", "opus": "audio/ogg", "aac": "audio/aac", "flac": "audio/flac", "wav": "audio/wav", "pcm": "audio/pcm"}


def openai_client(api_key: SecretStr, *, base_url: str | None = None, http_client: Any | None = None) -> Any:
    from openai import AsyncOpenAI  # lazy: install `openai` only if you use this provider

    return AsyncOpenAI(api_key=api_key.get_secret_value(), base_url=base_url, max_retries=0, http_client=http_client)


def translate_openai_error(error: Exception) -> VoiceError:
    """The SDK's exceptions -> `VoiceError`. 4xx that point at the audio are the client's fault;
    the rest is the provider's (or ours: a bad model name is 400 too, logged with its `param`)."""
    import openai

    kind = type(error).__name__
    if isinstance(error, openai.APITimeoutError):
        return VoiceError(VoiceErrorCode.TIMEOUT, retryable=True, kind=kind)
    if isinstance(error, openai.APIConnectionError):
        return VoiceError(VoiceErrorCode.UNAVAILABLE, retryable=True, kind=kind)
    if isinstance(error, openai.RateLimitError):
        return VoiceError(VoiceErrorCode.RATE_LIMITED, retryable=True, kind=kind)
    if isinstance(error, openai.APIStatusError):
        status = error.status_code
        if status in (413, 415):
            return VoiceError(VoiceErrorCode.INVALID_AUDIO, retryable=False, kind=kind)
        if status in (400, 422):
            body = error.body if isinstance(error.body, dict) else {}
            body = body.get("error", body) if isinstance(body.get("error"), dict) else body  # the SDK may unwrap it
            param, code = str(body.get("param") or ""), str(body.get("code") or "")
            if param == "file" or "audio" in param or code in ("audio_too_short", "unsupported_format"):
                return VoiceError(VoiceErrorCode.INVALID_AUDIO, retryable=False, kind=kind)
            logger.warning("openai rejected the request (status=%s, param=%s, code=%s)", status, param, code)
            return VoiceError(VoiceErrorCode.UNAVAILABLE, retryable=False, kind=kind)
        if status == 401:
            return VoiceError(VoiceErrorCode.UNAVAILABLE, retryable=False, kind=kind)
        return VoiceError(VoiceErrorCode.UNAVAILABLE, retryable=status >= 500, kind=kind)
    return VoiceError(VoiceErrorCode.UNAVAILABLE, retryable=True, kind=kind)


class OpenAITranscriber(Transcriber):
    engine = "openai"

    def __init__(self, client: Any, *, model: str = "gpt-4o-mini-transcribe", no_speech_threshold: float = 0.6, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = client
        self.model = model
        self.no_speech_threshold = no_speech_threshold

    async def _transcribe(self, audio: AudioInput, language: str | None) -> str:
        params: dict[str, Any] = {"file": (f"audio.{audio.extension}", audio.content), "model": self.model}
        if language:
            params["language"] = language
        if self.prompt:
            params["prompt"] = self.prompt
        if self.model.startswith("whisper"):
            # whisper-1 reports no_speech_prob per segment: the only signal it gives against hallucinated text
            result = await self._client.audio.transcriptions.create(response_format="verbose_json", **params)
            segments = getattr(result, "segments", None) or []
            if segments and all((getattr(s, "no_speech_prob", 0.0) or 0.0) >= self.no_speech_threshold for s in segments):
                return ""
            return result.text
        result = await self._client.audio.transcriptions.create(response_format="json", **params)
        return result.text

    def _translate(self, error: Exception) -> VoiceError:
        return translate_openai_error(error)

    async def close(self) -> None:
        await self._client.close()


class OpenAISynthesizer(Synthesizer):
    engine = "openai"

    def __init__(
        self,
        client: Any,
        *,
        model: str = "gpt-4o-mini-tts",
        audio_format: str = "mp3",
        voice: str = "nova",
        voices: Iterable[str] = OPENAI_VOICES,
        **kwargs: Any,
    ) -> None:
        super().__init__(voice=voice, voices=voices, **kwargs)
        self._client = client
        self.model = model
        self.audio_format = audio_format
        self.mime = SPEECH_MIME[audio_format]

    async def _synthesize(self, text: str, voice: str) -> bytes:
        response = await self._client.audio.speech.create(model=self.model, voice=voice, input=text, response_format=self.audio_format)
        return response.content

    def _translate(self, error: Exception) -> VoiceError:
        return translate_openai_error(error)

    async def close(self) -> None:
        await self._client.close()
