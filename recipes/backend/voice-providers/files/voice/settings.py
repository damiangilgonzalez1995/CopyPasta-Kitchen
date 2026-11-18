"""Voice settings BLOCK, meant to be mixed into the project settings (`project-settings`):

    class Settings(VoiceSettings, LLMSettings, BaseAppSettings): ...

Env vars:
    STT_PROVIDER=openai|fake            required
    STT_MODEL=gpt-4o-mini-transcribe    (whisper-1 adds the no_speech check; gpt-4o-transcribe is the accurate one)
    STT_LANGUAGE=es                     STT_PROMPT="vocabulario, siglas"   STT_MAX_BYTES=10485760   STT_TIMEOUT_SECONDS=60
    TTS_PROVIDER=openai|fake            required (delete tts if your app only dictates)
    TTS_MODEL=gpt-4o-mini-tts           TTS_VOICE=nova   TTS_FORMAT=mp3   TTS_MAX_CHARS=4096   TTS_TIMEOUT_SECONDS=60
    OPENAI_API_KEY=...                  same name as the `langchain-agent` block: one key
"""

from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import SttProvider, TtsProvider


class VoiceSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    stt_provider: SttProvider = Field(description="No default on purpose: the fake must be chosen, never fallen into.")
    stt_model: str = "gpt-4o-mini-transcribe"
    stt_language: str | None = Field(default="es", description="Hint for the provider. None = auto-detect.")
    stt_prompt: str | None = Field(default=None, description="Domain vocabulary and acronyms, as a sentence.")
    stt_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    stt_timeout_seconds: float = Field(default=60.0, gt=0)
    stt_no_speech_threshold: float = Field(default=0.6, ge=0, le=1, description="whisper-1 only.")

    tts_provider: TtsProvider
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "nova"
    tts_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "mp3"
    tts_max_chars: int = Field(default=4096, gt=0)
    tts_timeout_seconds: float = Field(default=60.0, gt=0)

    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = Field(default=None, description="An OpenAI-compatible endpoint (Groq, Azure...).")

    @model_validator(mode="after")
    def _openai_needs_its_key(self) -> "VoiceSettings":
        uses_openai = SttProvider.OPENAI is self.stt_provider or TtsProvider.OPENAI is self.tts_provider
        if uses_openai and self.openai_api_key is None:
            raise ValueError("STT_PROVIDER/TTS_PROVIDER=openai needs OPENAI_API_KEY")
        return self
