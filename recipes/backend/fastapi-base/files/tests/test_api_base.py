import logging

import httpx
import pytest
from fastapi import HTTPException

from api.base import build_app
from api.errors import ApiError, ErrorDetail
from api.logging_setup import FORMAT, configure_logging
from api.request_id import RequestIdFilter, current_request_id
from api.settings import ApiSettings


def make_app(**settings):
    """Straight from `build_app`, like any project's `create_app` does (so these tests also hold
    when another recipe has replaced `api/app.py`)."""
    api = ApiSettings(**settings)
    app = build_app(title="test", docs=api.docs_enabled, cors_origins=api.cors_origins)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("db password is hunter2")

    @app.get("/teapot")
    async def teapot():
        raise ApiError(418, "teapot", resets_at="never")

    @app.get("/plain")
    async def plain():
        raise HTTPException(404, "Not Found")

    @app.get("/whoami")
    async def whoami():
        return {"request_id": current_request_id()}

    return app


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_health_needs_nothing():
    async with client(make_app()) as c:
        response = await c.get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


async def test_every_response_carries_a_request_id_and_the_handler_sees_the_same_one():
    async with client(make_app()) as c:
        response = await c.get("/whoami")
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert len(response.headers["x-request-id"]) == 16
    assert current_request_id() == "-"  # reset after the request


async def test_client_request_id_is_kept_when_sane_and_replaced_otherwise():
    async with client(make_app()) as c:
        kept = await c.get("/health", headers={"X-Request-ID": "front-abc.123"})
        replaced = await c.get("/health", headers={"X-Request-ID": "x" * 65})
        injected = await c.get("/health", headers={"X-Request-ID": "a b\n"})
    assert kept.headers["x-request-id"] == "front-abc.123"
    assert replaced.headers["x-request-id"] != "x" * 65
    assert injected.headers["x-request-id"].isalnum()


async def test_unhandled_error_is_500_with_code_and_id_and_no_internals(caplog):
    async with client(make_app()) as c:
        with caplog.at_level(logging.ERROR):
            response = await c.get("/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "internal_error", "request_id": response.headers["x-request-id"]}}
    assert "hunter2" not in response.text
    assert "hunter2" in caplog.text and "RuntimeError" in caplog.text


async def test_api_error_and_plain_http_exception_keep_the_detail_envelope():
    async with client(make_app()) as c:
        teapot = await c.get("/teapot")
        plain = await c.get("/plain")
    assert teapot.status_code == 418 and teapot.json() == {"detail": {"code": "teapot", "resets_at": "never"}}
    assert ErrorDetail(**teapot.json()["detail"]).code == "teapot"
    assert plain.status_code == 404 and plain.json() == {"detail": "Not Found"}
    assert "x-request-id" in plain.headers


async def test_cors_only_when_origins_are_configured():
    preflight = {"Origin": "https://app.example", "Access-Control-Request-Method": "GET"}
    async with client(make_app()) as c:
        assert "access-control-allow-origin" not in (await c.options("/health", headers=preflight)).headers
    async with client(make_app(cors_origins="https://app.example, https://other.example")) as c:
        preflight_response = await c.options("/health", headers=preflight)
        assert preflight_response.headers["access-control-allow-origin"] == "https://app.example"
        real = await c.get("/health", headers={"Origin": "https://app.example"})
        assert "x-request-id" in real.headers["access-control-expose-headers"].lower()
        assert "access-control-allow-origin" not in (
            await c.get("/health", headers={"Origin": "https://evil.example"})
        ).headers


async def test_docs_hidden_unless_enabled():
    async with client(make_app()) as c:
        assert (await c.get("/docs")).status_code == 404
        assert (await c.get("/openapi.json")).status_code == 404
    async with client(make_app(docs_enabled=True)) as c:
        assert (await c.get("/openapi.json")).status_code == 200


def test_settings_parse_comma_separated_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, https://app.example")
    monkeypatch.setenv("DOCS_ENABLED", "true")
    settings = ApiSettings()
    assert settings.cors_origins == ["http://localhost:5173", "https://app.example"]
    assert settings.docs_enabled is True
    assert ApiSettings(cors_origins=[]).cors_origins == []


def test_logging_format_prints_the_request_id():
    configure_logging("DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG and any(isinstance(f, RequestIdFilter) for f in root.handlers[0].filters)
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    RequestIdFilter().filter(record)
    assert "[-] x: hello" in logging.Formatter(FORMAT).format(record)
    root.handlers = []  # leave pytest's own capture alone


@pytest.mark.parametrize("status", [400, 429])
def test_api_error_exposes_its_code(status):
    error = ApiError(status, "some_code", headers={"Retry-After": "5"}, retry_after=5)
    assert (error.status_code, error.code, error.detail, error.headers) == (
        status,
        "some_code",
        {"code": "some_code", "retry_after": 5},
        {"Retry-After": "5"},
    )
