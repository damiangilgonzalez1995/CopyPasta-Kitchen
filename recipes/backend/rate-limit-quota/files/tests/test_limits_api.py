"""The guard and GET /agent/quota on the real app. Needs agent-chat-api (and what it requires)
copied next to `limits/`, with this recipe's `api/agent/guards.py` in place."""

import httpx
import pytest
from langchain_core.messages import AIMessage

from agentic.agents import AssistantAgent
from agentic.memory import InMemoryMemory
from agentic.registry import registry
from api.agent.settings import AgentApiSettings
from api.app import create_app
from api.auth import StaticTokenVerifier
from api.limits.router import router as quota_router
from limits import InMemoryQuotaStore, InMemoryRateLimiter, QuotaLimits, QuotaUnit, TurnLimits

from .fakes import ScriptedChatModel
from .limits_conformance import FakeClock
from .test_agent_api import TOKENS, auth, classifier_answering


def make_app(limits: TurnLimits | None):
    app = create_app(
        settings=AgentApiSettings(),
        token_verifier=StaticTokenVerifier(TOKENS),
        memory=InMemoryMemory(),
        document_search=None,
    )
    app.state.turn_limits = limits
    app.include_router(quota_router)
    return app


def limits_for_tests(clock: FakeClock, *, daily: float | None = 2, per_minute: int = 1) -> TurnLimits:
    return TurnLimits(
        quota=InMemoryQuotaStore(limits=QuotaLimits(daily=daily), clock=clock),
        rate_limiter=InMemoryRateLimiter(max_requests=per_minute, window_seconds=60, clock=clock),
        unit=QuotaUnit.REQUESTS,
    )


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def answering_agents():
    registry.reset()
    registry.override(
        classifier=classifier_answering("technical"),
        assistant=AssistantAgent(llm=ScriptedChatModel(responses=[AIMessage("ok")] * 5), tools=[]),
    )
    yield
    registry.reset()


async def test_without_limits_everything_passes_and_quota_is_available():
    app = make_app(None)
    async with client(app) as c:
        assert (await c.post("/agent/chat", json={"question": "hola"}, headers=auth())).status_code == 200
        assert (await c.get("/agent/quota", headers=auth())).json() == {"available": True, "exhausted": None, "resets_at": None}


async def test_rate_limited_turn_is_429_with_code_and_retry_after():
    clock = FakeClock()
    app = make_app(limits_for_tests(clock))
    async with client(app) as c:
        assert (await c.post("/agent/chat", json={"question": "hola"}, headers=auth())).status_code == 200
        clock.advance(15)
        response = await c.post("/agent/stream", json={"question": "otra"}, headers=auth())

    assert response.status_code == 429
    assert response.headers["retry-after"] == "45"
    detail = response.json()["detail"]
    assert detail["code"] == "rate_limited" and detail["retry_after"] == 45
    assert detail["resets_at"] == "2026-03-30T10:01:00+00:00"


async def test_exhausted_quota_is_429_and_get_quota_says_until_when():
    clock = FakeClock()
    app = make_app(limits_for_tests(clock, daily=1, per_minute=10))
    async with client(app) as c:
        assert (await c.post("/agent/chat", json={"question": "hola"}, headers=auth())).status_code == 200
        refused = await c.post("/agent/chat", json={"question": "otra"}, headers=auth())
        quota = await c.get("/agent/quota", headers=auth())
        other_tenant = await c.get("/agent/quota", headers=auth("tok-bob"))

    assert refused.status_code == 429
    assert refused.json()["detail"] == {"code": "ai_quota_daily_exhausted", "resets_at": "2026-03-31T00:00:00+00:00"}
    assert quota.json() == {"available": False, "exhausted": "daily", "resets_at": "2026-03-31T00:00:00Z"}
    assert other_tenant.json()["available"] is True


async def test_quota_route_has_the_same_guards_as_the_chat():
    app = make_app(None)
    async with client(app) as c:
        assert (await c.get("/agent/quota")).status_code == 401
    app.state.agent_api_settings = AgentApiSettings(agent_endpoint_enabled=False)
    async with client(app) as c:
        assert (await c.get("/agent/quota", headers=auth())).status_code == 404
