import wave
import io

import pytest
from pydantic import SecretStr

from voice import AudioInput, SttProvider, TtsProvider, VoiceError, VoiceErrorCode, VoiceFactory, VoiceSettings
from voice.fake import FakeSynthesizer, FakeTranscriber
from voice.openai_provider import OpenAISynthesizer, OpenAITranscriber, translate_openai_error

from .fake_openai import FakeOpenAI
from .voice_conformance import SILENCE, WEBM, SynthesizerConformance, TranscriberConformance


def settings(**overrides) -> VoiceSettings:
    base = {"stt_provider": "fake", "tts_provider": "fake"}
    return VoiceSettings(_env_file=None, **{**base, **overrides})


def openai_settings(fake: FakeOpenAI, **overrides) -> VoiceSettings:
    return settings(stt_provider="openai", tts_provider="openai", openai_api_key="sk-test", **overrides)


# --- providers through the conformance batteries -------------------------------------------


class TestFakeTranscriber(TranscriberConformance):
    @pytest.fixture
    def transcriber(self):
        return FakeTranscriber(text="hola mundo", language="es")


class TestOpenAITranscriber(TranscriberConformance):
    @pytest.fixture
    def transcriber(self):
        fake = FakeOpenAI(text="hola mundo")

        class Silent(FakeOpenAI):
            def _handle(self, request):
                if b"SILENCE" in request.read():
                    self.text = ""
                return super()._handle(request)

        return VoiceFactory.transcriber(openai_settings(fake), http_client=Silent(text="hola mundo").http_client)


class TestFakeSynthesizer(SynthesizerConformance):
    @pytest.fixture
    def synthesizer(self):
        return FakeSynthesizer()


class TestOpenAISynthesizer(SynthesizerConformance):
    @pytest.fixture
    def synthesizer(self):
        return VoiceFactory.synthesizer(openai_settings(FakeOpenAI()), http_client=FakeOpenAI().http_client)


# --- what is sent to OpenAI ------------------------------------------------------------------


async def test_openai_transcriber_sends_file_model_language_and_prompt():
    fake = FakeOpenAI(text="  hola mundo ")
    transcriber = VoiceFactory.transcriber(
        openai_settings(fake, stt_model="gpt-4o-mini-transcribe", stt_language="es", stt_prompt="ATI, Vera"), http_client=fake.http_client
    )
    result = await transcriber.transcribe(AudioInput(content=b"...", mime="audio/mp4; codecs=mp4a"), language="pt")
    assert result.text == "hola mundo" and result.language == "pt" and result.engine == "openai"
    sent = fake.requests[0]
    assert sent["path"].endswith("/audio/transcriptions") and sent["filename"] == "audio.mp4"
    assert sent["fields"]["model"] == "gpt-4o-mini-transcribe" and sent["fields"]["language"] == "pt"
    assert sent["fields"]["prompt"] == "ATI, Vera" and sent["fields"]["response_format"] == "json"


async def test_whisper_uses_verbose_json_and_drops_hallucinations_on_silence():
    noisy = FakeOpenAI(text="Subtítulos por Amara.org", segments=[{"no_speech_prob": 0.95, "text": "x"}, {"no_speech_prob": 0.7, "text": "y"}])
    transcriber = VoiceFactory.transcriber(openai_settings(noisy, stt_model="whisper-1"), http_client=noisy.http_client)
    assert (await transcriber.transcribe(WEBM)).text == ""
    assert noisy.requests[0]["fields"]["response_format"] == "verbose_json"
    speech = FakeOpenAI(text="hola", segments=[{"no_speech_prob": 0.95, "text": "x"}, {"no_speech_prob": 0.1, "text": "hola"}])
    transcriber = VoiceFactory.transcriber(openai_settings(speech, stt_model="whisper-1"), http_client=speech.http_client)
    assert (await transcriber.transcribe(WEBM)).text == "hola"


async def test_openai_synthesizer_sends_model_voice_and_format():
    fake = FakeOpenAI()
    synthesizer = VoiceFactory.synthesizer(openai_settings(fake, tts_model="tts-1-hd", tts_voice="nova", tts_format="mp3"), http_client=fake.http_client)
    speech = await synthesizer.synthesize("Hola", voice="echo")
    assert speech.audio.startswith(b"ID3") and speech.mime == "audio/mpeg"
    assert fake.requests[0]["json"] == {"model": "tts-1-hd", "voice": "echo", "input": "Hola", "response_format": "mp3"}


@pytest.mark.parametrize(
    "status, body, code, retryable",
    [
        (429, None, VoiceErrorCode.RATE_LIMITED, True),
        (413, None, VoiceErrorCode.INVALID_AUDIO, False),
        (415, None, VoiceErrorCode.INVALID_AUDIO, False),
        (400, {"error": {"message": "audio too short", "param": "file", "type": "x", "code": "audio_too_short"}}, VoiceErrorCode.INVALID_AUDIO, False),
        (400, {"error": {"message": "bad model", "param": "model", "type": "x", "code": None}}, VoiceErrorCode.UNAVAILABLE, False),
        (401, None, VoiceErrorCode.UNAVAILABLE, False),
        (500, None, VoiceErrorCode.UNAVAILABLE, True),
        (503, None, VoiceErrorCode.UNAVAILABLE, True),
    ],
)
async def test_openai_http_errors_become_voice_errors_without_the_message(status, body, code, retryable, caplog):
    fake = FakeOpenAI(status=status, body=body)
    transcriber = VoiceFactory.transcriber(openai_settings(fake), http_client=fake.http_client)
    with pytest.raises(VoiceError) as info:
        await transcriber.transcribe(WEBM)
    assert (info.value.code, info.value.retryable) == (code, retryable)
    assert "nope" not in str(info.value) and "nope" not in caplog.text and info.value.kind.endswith("Error")


def test_translate_connection_and_timeout_errors():
    import httpx
    import openai

    request = httpx.Request("POST", "http://x")
    assert translate_openai_error(openai.APITimeoutError(request)).code is VoiceErrorCode.TIMEOUT
    connection = translate_openai_error(openai.APIConnectionError(request=request))
    assert connection.code is VoiceErrorCode.UNAVAILABLE and connection.retryable


# --- fakes, settings and factory ----------------------------------------------------------------


async def test_fake_synthesizer_returns_a_valid_wav_that_grows_with_the_text():
    short = await FakeSynthesizer().synthesize("hola")
    long = await FakeSynthesizer().synthesize("hola " * 20)
    with wave.open(io.BytesIO(short.audio)) as wav:
        assert wav.getnchannels() == 1 and wav.getframerate() == 8000 and wav.getnframes() == 8000 * 4 * 50 // 1000
    assert len(long.audio) > len(short.audio) and short.mime == "audio/wav"


async def test_fake_transcriber_records_calls_and_silence():
    transcriber = FakeTranscriber(text="dictado")
    assert (await transcriber.transcribe(WEBM)).text == "dictado"
    assert (await transcriber.transcribe(SILENCE)).text == ""
    assert [a.mime for a, _ in transcriber.calls] == ["audio/webm", "audio/wav"]


def test_settings_require_providers_and_the_key_for_openai():
    with pytest.raises(ValueError, match="stt_provider"):
        VoiceSettings(_env_file=None, tts_provider="fake")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        settings(stt_provider="openai")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        settings(tts_provider="openai")
    s = settings(stt_provider="openai", openai_api_key="sk-x", stt_language=None, tts_format="wav")
    assert s.stt_provider is SttProvider.OPENAI and s.tts_provider is TtsProvider.FAKE and s.stt_language is None
    assert s.stt_max_bytes == 10 * 1024 * 1024 and s.tts_max_chars == 4096 and s.tts_format == "wav"


def test_factory_builds_the_configured_providers_with_their_settings():
    s = settings(stt_language="en", stt_prompt="p", stt_max_bytes=99, stt_timeout_seconds=1.5, tts_voice="v", tts_max_chars=10)
    transcriber, synthesizer = VoiceFactory.transcriber(s), VoiceFactory.synthesizer(s)
    assert isinstance(transcriber, FakeTranscriber) and (transcriber.language, transcriber.prompt, transcriber.max_bytes, transcriber.timeout_seconds) == ("en", "p", 99, 1.5)
    assert isinstance(synthesizer, FakeSynthesizer) and (synthesizer.voice, synthesizer.max_chars) == ("v", 10)

    o = settings(stt_provider="openai", tts_provider="openai", openai_api_key=SecretStr("sk-x"), stt_model="whisper-1", tts_format="opus")
    assert isinstance(VoiceFactory.transcriber(o), OpenAITranscriber) and VoiceFactory.transcriber(o).model == "whisper-1"
    synthesizer = VoiceFactory.synthesizer(o)
    assert isinstance(synthesizer, OpenAISynthesizer) and synthesizer.mime == "audio/ogg" and "nova" in synthesizer.voices
