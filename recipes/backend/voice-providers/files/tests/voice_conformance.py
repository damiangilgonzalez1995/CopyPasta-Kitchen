"""Behaviour every `Transcriber` / `Synthesizer` must have. A new provider = a subclass with the fixture.

    class TestDeepgramTranscriber(TranscriberConformance):
        @pytest.fixture
        def transcriber(self): return DeepgramTranscriber(...)   # must answer "hola mundo" for WEBM and "" for SILENCE
"""

import asyncio

import pytest

from voice import AudioInput, Speech, Transcription, VoiceError, VoiceErrorCode

WEBM = AudioInput(content=b"\x1aE\xdf\xa3fake-webm", mime="audio/webm")
SILENCE = AudioInput(content=b"SILENCE", mime="audio/wav")


class TranscriberConformance:
    async def test_returns_a_transcription_with_engine_and_timing(self, transcriber):
        result = await transcriber.transcribe(WEBM)
        assert isinstance(result, Transcription) and result.text == "hola mundo" and result.engine
        assert result.duration_ms >= 0 and result.language == transcriber.language

    async def test_silence_is_empty_text_not_an_error(self, transcriber):
        assert (await transcriber.transcribe(SILENCE)).text == ""

    async def test_language_of_the_call_wins(self, transcriber):
        assert (await transcriber.transcribe(WEBM, language="en")).language == "en"

    @pytest.mark.parametrize(
        "audio, kind",
        [
            (AudioInput(content=b"", mime="audio/webm"), "EmptyAudio"),
            (AudioInput(content=b"x", mime="audio/aac"), "UnsupportedFormat"),
            (AudioInput(content=b"x", mime="text/plain"), "UnsupportedFormat"),
        ],
    )
    async def test_invalid_audio_is_rejected_before_the_provider(self, transcriber, audio, kind):
        with pytest.raises(VoiceError) as info:
            await transcriber.transcribe(audio)
        assert info.value.code is VoiceErrorCode.INVALID_AUDIO and info.value.kind == kind and not info.value.retryable

    async def test_size_limit(self, transcriber):
        transcriber.max_bytes = 4
        with pytest.raises(VoiceError, match="AudioTooLarge"):
            await transcriber.transcribe(WEBM)

    async def test_timeout_becomes_a_retryable_voice_error(self, transcriber, monkeypatch):
        async def slow(*args, **kwargs):
            await asyncio.sleep(1)
            return "late"

        monkeypatch.setattr(transcriber, "_transcribe", slow)
        transcriber.timeout_seconds = 0.01
        with pytest.raises(VoiceError) as info:
            await transcriber.transcribe(WEBM)
        assert info.value.code is VoiceErrorCode.TIMEOUT and info.value.retryable


class SynthesizerConformance:
    async def test_returns_playable_bytes_with_mime(self, synthesizer):
        speech = await synthesizer.synthesize("Hola, ¿qué tal?")
        assert isinstance(speech, Speech) and len(speech.audio) > 0 and speech.mime.startswith("audio/")
        assert speech.engine and speech.duration_ms >= 0

    async def test_empty_and_too_long_text(self, synthesizer):
        with pytest.raises(VoiceError) as empty:
            await synthesizer.synthesize("   ")
        assert empty.value.code is VoiceErrorCode.EMPTY_TEXT
        synthesizer.max_chars = 5
        with pytest.raises(VoiceError) as long:
            await synthesizer.synthesize("demasiado largo")
        assert long.value.code is VoiceErrorCode.TEXT_TOO_LONG and not long.value.retryable

    async def test_unknown_voice_is_rejected_when_there_is_an_allowlist(self, synthesizer):
        if not synthesizer.voices:
            pytest.skip("this provider accepts any voice")
        with pytest.raises(VoiceError) as info:
            await synthesizer.synthesize("hola", voice="not-a-voice")
        assert info.value.code is VoiceErrorCode.INVALID_VOICE
