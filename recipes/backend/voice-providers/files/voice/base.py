"""`Transcriber` (speech -> text) and `Synthesizer` (text -> speech): the contracts.

Both are template methods: the public call validates the input, measures, bounds the time and
translates every failure into `VoiceError`; the subclass only talks to its provider in
`_transcribe` / `_synthesize`. Nothing here retries: `VoiceError.retryable` tells the caller.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable

from .models import AudioInput, Speech, Transcription, VoiceError, VoiceErrorCode

logger = logging.getLogger(__name__)


class Transcriber(ABC):
    engine: str = "transcriber"

    def __init__(
        self,
        *,
        language: str | None = None,
        prompt: str | None = None,
        max_bytes: int = 10 * 1024 * 1024,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.language = language
        self.prompt = prompt
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds

    async def transcribe(self, audio: AudioInput, *, language: str | None = None) -> Transcription:
        """`language=None` -> the one configured. Empty text = no speech."""
        if not audio.content:
            raise VoiceError(VoiceErrorCode.INVALID_AUDIO, retryable=False, kind="EmptyAudio")
        if audio.extension is None:
            raise VoiceError(VoiceErrorCode.INVALID_AUDIO, retryable=False, kind="UnsupportedFormat")
        if len(audio.content) > self.max_bytes:
            raise VoiceError(VoiceErrorCode.INVALID_AUDIO, retryable=False, kind="AudioTooLarge")
        lang = language or self.language
        started = time.monotonic()
        text = await _bounded(self._transcribe(audio, lang), self.timeout_seconds, self.engine, self._translate)
        if not isinstance(text, str):
            raise VoiceError(VoiceErrorCode.UNAVAILABLE, retryable=False, kind="InvalidProviderOutput")
        return Transcription(
            text=text.strip(), language=lang, engine=self.engine, duration_ms=int((time.monotonic() - started) * 1000)
        )

    @abstractmethod
    async def _transcribe(self, audio: AudioInput, language: str | None) -> str: ...

    def _translate(self, error: Exception) -> VoiceError:
        """Map the provider's exceptions to `VoiceError`. Override per provider."""
        return VoiceError(VoiceErrorCode.UNAVAILABLE, retryable=True, kind=type(error).__name__)

    async def close(self) -> None:
        return None


class Synthesizer(ABC):
    engine: str = "synthesizer"
    mime: str = "audio/mpeg"

    def __init__(
        self,
        *,
        voice: str,
        voices: Iterable[str] = (),
        max_chars: int = 4096,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.voice = voice
        self.voices = frozenset(voices)  # empty = any voice is accepted
        self.max_chars = max_chars
        self.timeout_seconds = timeout_seconds

    async def synthesize(self, text: str, *, voice: str | None = None) -> Speech:
        text = text.strip()
        if not text:
            raise VoiceError(VoiceErrorCode.EMPTY_TEXT, retryable=False)
        if len(text) > self.max_chars:
            raise VoiceError(VoiceErrorCode.TEXT_TOO_LONG, retryable=False)
        chosen = voice or self.voice
        if self.voices and chosen not in self.voices:
            raise VoiceError(VoiceErrorCode.INVALID_VOICE, retryable=False)
        started = time.monotonic()
        audio = await _bounded(self._synthesize(text, chosen), self.timeout_seconds, self.engine, self._translate)
        if not isinstance(audio, bytes | bytearray) or not audio:
            raise VoiceError(VoiceErrorCode.UNAVAILABLE, retryable=False, kind="InvalidProviderOutput")
        return Speech(audio=bytes(audio), mime=self.mime, engine=self.engine, duration_ms=int((time.monotonic() - started) * 1000))

    @abstractmethod
    async def _synthesize(self, text: str, voice: str) -> bytes: ...

    def _translate(self, error: Exception) -> VoiceError:
        return VoiceError(VoiceErrorCode.UNAVAILABLE, retryable=True, kind=type(error).__name__)

    async def close(self) -> None:
        return None


async def _bounded(awaitable, timeout: float, engine: str, translate):
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except VoiceError:
        raise
    except TimeoutError:
        logger.warning("%s timed out after %.0fs", engine, timeout)
        raise VoiceError(VoiceErrorCode.TIMEOUT, retryable=True, kind="TimeoutError") from None
    except Exception as exc:  # the message may hold the key or the URL: class name only
        error = translate(exc)
        logger.warning("%s failed: %s -> %s", engine, type(exc).__name__, error.code.value)
        raise error from None
