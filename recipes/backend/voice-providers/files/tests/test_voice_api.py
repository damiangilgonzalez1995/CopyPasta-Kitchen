"""Needs `fastapi-base` (build_app, ApiError) and `auth-verifier` (api/auth.py) copied next to this recipe."""

import httpx
import pytest

pytest.importorskip("api.base")
pytest.importorskip("api.auth")

from api.auth import CurrentUser, StaticTokenVerifier  # noqa: E402
from api.base import build_app  # noqa: E402
from api.voice.router import router  # noqa: E402
from voice import VoiceError, VoiceErrorCode  # noqa: E402
from voice.fake import FakeSynthesizer, FakeTranscriber  # noqa: E402

AUTH = {"Authorization": "Bearer tok"}


def make_app(transcriber=None, synthesizer=None):
    app = build_app(title="test")
    app.state.token_verifier = StaticTokenVerifier({"tok": CurrentUser(id="u1", tenant_id="t1")})
    app.state.transcriber = transcriber
    app.state.synthesizer = synthesizer
    app.include_router(router)
    return app


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def upload(content: bytes, mime: str = "audio/webm", **form):
    return {"files": {"file": ("rec.webm", content, mime)}, "data": form}


async def test_transcribe_returns_text_and_stores_nothing():
    transcriber = FakeTranscriber(text="hola mundo", language="es")
    async with client(make_app(transcriber=transcriber)) as c:
        response = await c.post("/voice/transcribe", headers=AUTH, **upload(b"\x1aE\xdf\xa3...", "audio/webm;codecs=opus", language="en"))
    assert response.status_code == 200 and response.json() == {"text": "hola mundo", "language": "en"}
    assert transcriber.calls[0][0].mime == "audio/webm" and transcriber.calls[0][1] == "en"


async def test_transcribe_requires_auth():
    async with client(make_app(transcriber=FakeTranscriber())) as c:
        assert (await c.post("/voice/transcribe", **upload(b"x"))).status_code == 401


@pytest.mark.parametrize(
    "kwargs, status, code",
    [
        (upload(b"x", "audio/aac"), 415, "unsupported_audio_format"),
        (upload(b"x" * 100, "audio/webm"), 413, "audio_too_large"),
        (upload(b"", "audio/webm"), 422, "empty_audio"),
        (upload(b"SILENCE", "audio/wav"), 422, "no_speech"),
        (upload(b"x", "audio/webm", language="español"), 422, "invalid_language"),
    ],
)
async def test_transcribe_rejections_have_a_code(kwargs, status, code):
    async with client(make_app(transcriber=FakeTranscriber(max_bytes=50))) as c:
        response = await c.post("/voice/transcribe", headers=AUTH, **kwargs)
    assert (response.status_code, response.json()["detail"]["code"]) == (status, code)


class Failing(FakeTranscriber):
    def __init__(self, error: VoiceError) -> None:
        super().__init__()
        self.error = error

    async def _transcribe(self, audio, language):
        raise self.error


@pytest.mark.parametrize(
    "error, status, code",
    [
        (VoiceError(VoiceErrorCode.RATE_LIMITED, retryable=True), 429, "provider_rate_limited"),
        (VoiceError(VoiceErrorCode.TIMEOUT, retryable=True), 504, "provider_timeout"),
        (VoiceError(VoiceErrorCode.UNAVAILABLE, retryable=True), 502, "provider_unavailable"),
        (VoiceError(VoiceErrorCode.UNAVAILABLE, retryable=False), 503, "provider_unavailable"),
        (VoiceError(VoiceErrorCode.INVALID_AUDIO, retryable=False), 422, "invalid_audio"),
    ],
)
async def test_provider_failures_map_to_http(error, status, code):
    async with client(make_app(transcriber=Failing(error))) as c:
        response = await c.post("/voice/transcribe", headers=AUTH, **upload(b"x"))
    assert (response.status_code, response.json()["detail"]["code"]) == (status, code)
    assert "x-request-id" in response.headers
    if status == 429:
        assert response.headers["retry-after"] == "5"


async def test_synthesize_returns_audio_with_no_store():
    async with client(make_app(synthesizer=FakeSynthesizer())) as c:
        ok = await c.post("/voice/synthesize", headers=AUTH, json={"text": "Hola", "voice": "any"})
        empty = await c.post("/voice/synthesize", headers=AUTH, json={"text": "   "})
        unauth = await c.post("/voice/synthesize", json={"text": "Hola"})
    assert ok.status_code == 200 and ok.headers["content-type"] == "audio/wav" and ok.headers["cache-control"] == "no-store"
    assert ok.content[:4] == b"RIFF"
    assert (empty.status_code, empty.json()["detail"]["code"]) == (422, "empty_text") and unauth.status_code == 401


async def test_app_without_voice_answers_503():
    async with client(make_app()) as c:
        t = await c.post("/voice/transcribe", headers=AUTH, **upload(b"x"))
        s = await c.post("/voice/synthesize", headers=AUTH, json={"text": "Hola"})
    assert t.status_code == 503 and s.status_code == 503 and t.json()["detail"]["code"] == "voice_unavailable"
