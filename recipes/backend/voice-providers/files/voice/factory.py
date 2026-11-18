"""The one place that builds the transcriber and the synthesizer the settings name."""

from typing import Any

from .base import Synthesizer, Transcriber
from .models import SttProvider, TtsProvider
from .settings import VoiceSettings


class VoiceFactory:
    @staticmethod
    def transcriber(settings: VoiceSettings, *, http_client: Any | None = None) -> Transcriber:
        """Call it once at startup: `app.state.transcriber = VoiceFactory.transcriber(settings)`.
        `http_client` is the test seam (httpx.MockTransport). Unknown provider -> ValueError."""
        common = {
            "language": settings.stt_language,
            "prompt": settings.stt_prompt,
            "max_bytes": settings.stt_max_bytes,
            "timeout_seconds": settings.stt_timeout_seconds,
        }
        match settings.stt_provider:
            case SttProvider.FAKE:
                from .fake import FakeTranscriber

                return FakeTranscriber(**common)
            case SttProvider.OPENAI:
                from .openai_provider import OpenAITranscriber, openai_client

                assert settings.openai_api_key is not None  # the settings validator guarantees it
                client = openai_client(settings.openai_api_key, base_url=settings.openai_base_url, http_client=http_client)
                return OpenAITranscriber(client, model=settings.stt_model, no_speech_threshold=settings.stt_no_speech_threshold, **common)
        raise ValueError(f"Unknown STT provider: {settings.stt_provider!r}")

    @staticmethod
    def synthesizer(settings: VoiceSettings, *, http_client: Any | None = None) -> Synthesizer:
        common = {"voice": settings.tts_voice, "max_chars": settings.tts_max_chars, "timeout_seconds": settings.tts_timeout_seconds}
        match settings.tts_provider:
            case TtsProvider.FAKE:
                from .fake import FakeSynthesizer

                return FakeSynthesizer(**common)
            case TtsProvider.OPENAI:
                from .openai_provider import OpenAISynthesizer, openai_client

                assert settings.openai_api_key is not None
                client = openai_client(settings.openai_api_key, base_url=settings.openai_base_url, http_client=http_client)
                return OpenAISynthesizer(client, model=settings.tts_model, audio_format=settings.tts_format, **common)
        raise ValueError(f"Unknown TTS provider: {settings.tts_provider!r}")
