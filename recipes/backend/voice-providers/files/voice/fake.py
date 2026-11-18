"""Test doubles and local provider (`STT_PROVIDER=fake`): no network, deterministic.

`FakeTranscriber` returns a fixed text, or "" when the audio is the literal `b"SILENCE"`.
`FakeSynthesizer` returns a valid WAV of silence whose length grows with the text, so a client
can actually play it.
"""

import io
import struct
import wave

from .base import Synthesizer, Transcriber
from .models import AudioInput


class FakeTranscriber(Transcriber):
    engine = "fake"

    def __init__(self, text: str = "test transcription", **kwargs) -> None:
        super().__init__(**kwargs)
        self.text = text
        self.calls: list[tuple[AudioInput, str | None]] = []

    async def _transcribe(self, audio: AudioInput, language: str | None) -> str:
        self.calls.append((audio, language))
        return "" if audio.content == b"SILENCE" else self.text


class FakeSynthesizer(Synthesizer):
    engine = "fake"
    mime = "audio/wav"

    def __init__(self, *, voice: str = "fake", ms_per_char: int = 50, **kwargs) -> None:
        super().__init__(voice=voice, **kwargs)
        self.ms_per_char = ms_per_char
        self.calls: list[tuple[str, str]] = []

    async def _synthesize(self, text: str, voice: str) -> bytes:
        self.calls.append((text, voice))
        return silence_wav(milliseconds=len(text) * self.ms_per_char)


def silence_wav(*, milliseconds: int, sample_rate: int = 8000) -> bytes:
    frames = max(1, sample_rate * milliseconds // 1000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(struct.pack(f"<{frames}h", *([0] * frames)))
    return buffer.getvalue()
