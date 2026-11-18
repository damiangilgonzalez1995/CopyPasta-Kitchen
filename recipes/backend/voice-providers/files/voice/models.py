"""Data of the voice layer. The audio never touches disk: `AudioInput` is bytes plus its MIME."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SttProvider(StrEnum):
    OPENAI = "openai"
    FAKE = "fake"


class TtsProvider(StrEnum):
    OPENAI = "openai"
    FAKE = "fake"


class VoiceErrorCode(StrEnum):
    INVALID_AUDIO = "invalid_audio"  # format, size, empty, too short: the client's fault
    EMPTY_TEXT = "empty_text"
    TEXT_TOO_LONG = "text_too_long"
    INVALID_VOICE = "invalid_voice"
    RATE_LIMITED = "rate_limited"  # the provider's 429
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"  # provider down, misconfigured or 5xx


class VoiceError(Exception):
    """The only error the voice layer raises. `kind` is the class name of the underlying error,
    never its text (it may hold the API key). `retryable` is for the caller: the provider never retries."""

    def __init__(self, code: VoiceErrorCode, *, retryable: bool, kind: str | None = None) -> None:
        super().__init__(code.value if kind is None else f"{code.value} ({kind})")
        self.code = code
        self.retryable = retryable
        self.kind = kind


# MIME -> extension the providers understand. What `MediaRecorder` produces (webm/opus, mp4 on
# Safari, ogg on Firefox) plus the usual files. `audio/aac` is left out: OpenAI rejects it.
AUDIO_FORMATS: dict[str, str] = {
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/mp4": "mp4",
    "video/mp4": "mp4",
    "audio/x-m4a": "m4a",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
}


class AudioInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: bytes
    mime: str = Field(description="Media type without parameters: 'audio/webm', not 'audio/webm;codecs=opus'.")

    @property
    def extension(self) -> str | None:
        return AUDIO_FORMATS.get(self.mime.split(";")[0].strip().lower())


class Transcription(BaseModel):
    """`text == ""` means no speech was detected: the caller decides what that is (422, skip...)."""

    model_config = ConfigDict(frozen=True)

    text: str
    language: str | None = Field(default=None, description="The language asked for or detected, if known.")
    engine: str
    duration_ms: int


class Speech(BaseModel):
    model_config = ConfigDict(frozen=True)

    audio: bytes
    mime: str
    engine: str
    duration_ms: int = Field(description="Time the provider took, not the length of the audio.")
