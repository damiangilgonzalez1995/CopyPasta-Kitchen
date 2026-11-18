"""Speech to text and text to speech with the provider chosen in settings.

    transcriber = VoiceFactory.transcriber(settings)           # startup, once; app.state.transcriber
    result = await transcriber.transcribe(AudioInput(content=data, mime="audio/webm"))
    if not result.text: ...                                    # no speech
    speech = await synthesizer.synthesize("Hola")              # Speech(audio=bytes, mime="audio/mpeg")

Every failure is a `VoiceError(code, retryable)`; `api/voice/router.py` maps the codes to HTTP.
"""

from .base import Synthesizer, Transcriber
from .factory import VoiceFactory
from .models import AUDIO_FORMATS, AudioInput, Speech, SttProvider, Transcription, TtsProvider, VoiceError, VoiceErrorCode
from .settings import VoiceSettings

__all__ = [
    "AUDIO_FORMATS",
    "AudioInput",
    "Speech",
    "SttProvider",
    "Synthesizer",
    "Transcriber",
    "Transcription",
    "TtsProvider",
    "VoiceError",
    "VoiceErrorCode",
    "VoiceFactory",
    "VoiceSettings",
]
