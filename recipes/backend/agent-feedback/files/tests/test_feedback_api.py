"""Feedback routes over the app from agent-chat-api, with an in-memory memory and store.
Needs agent-chat-api (and what it requires) copied next to `feedback/`."""

import httpx
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agentic.memory import InMemoryMemory, MemoryKey
from api.agent.settings import AgentApiSettings
from api.app import create_app
from api.auth import StaticTokenVerifier
from api.feedback.router import router as feedback_router
from feedback import InMemoryFeedbackStore

from .feedback_conformance import FakeClock
from .test_agent_api import TOKENS, auth

ALICE = MemoryKey(tenant_id="tenant-1", user_id="user-1", conversation_id="conv-1")
THREAD = [
    HumanMessage("busca algo", id="h1"),
    AIMessage("", id="call1", tool_calls=[{"name": "search", "args": {}, "id": "t1"}]),
    ToolMessage("resultado", tool_call_id="t1", id="tool1"),
    AIMessage("Encontré esto", id="a1"),
]


async def make_app(enabled: bool = True):
    memory = InMemoryMemory()
    await memory.add_messages(ALICE, THREAD)
    app = create_app(
        settings=AgentApiSettings(agent_endpoint_enabled=enabled),
        token_verifier=StaticTokenVerifier(TOKENS),
        memory=memory,
        document_search=None,
    )
    app.state.feedback_store = InMemoryFeedbackStore(clock=FakeClock())
    app.include_router(feedback_router)
    return app


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


VOTE = {"conversation_id": "conv-1", "message_id": "a1", "rating": 1}


async def test_guards_401_and_404_when_the_agent_is_off():
    app = await make_app()
    async with client(app) as c:
        assert (await c.post("/agent/feedback", json=VOTE)).status_code == 401
    app = await make_app(enabled=False)
    async with client(app) as c:
        assert (await c.post("/agent/feedback", json=VOTE, headers=auth())).status_code == 404


async def test_vote_then_revote_is_created_then_updated():
    app = await make_app()
    async with client(app) as c:
        first = await c.post("/agent/feedback", json={**VOTE, "comment": "útil"}, headers=auth())
        second = await c.post("/agent/feedback", json={**VOTE, "rating": -1}, headers=auth())
        listed = await c.get("/agent/feedback?conversation_id=conv-1", headers=auth())

    assert first.status_code == 200
    assert first.json() == {
        "message_id": "a1",
        "conversation_id": "conv-1",
        "rating": 1,
        "comment": "útil",
        "updated_at": "2026-03-30T10:00:00Z",
        "created_or_updated": "created",
    }
    assert (second.json()["rating"], second.json()["comment"], second.json()["created_or_updated"]) == (-1, None, "updated")
    assert [f["message_id"] for f in listed.json()["feedback"]] == ["a1"]


async def test_only_answers_in_your_own_conversation_can_be_voted():
    app = await make_app()
    async with client(app) as c:
        human = await c.post("/agent/feedback", json={**VOTE, "message_id": "h1"}, headers=auth())
        tool_call = await c.post("/agent/feedback", json={**VOTE, "message_id": "call1"}, headers=auth())
        unknown = await c.post("/agent/feedback", json={**VOTE, "message_id": "zzz"}, headers=auth())
        other_user = await c.post("/agent/feedback", json=VOTE, headers=auth("tok-bob"))
        bad_rating = await c.post("/agent/feedback", json={**VOTE, "rating": 0}, headers=auth())

    assert [r.status_code for r in (human, tool_call, unknown, other_user)] == [404] * 4
    assert bad_rating.status_code == 422


async def test_undo_removes_the_vote():
    app = await make_app()
    async with client(app) as c:
        await c.post("/agent/feedback", json=VOTE, headers=auth())
        assert (await c.delete("/agent/feedback/a1", headers=auth())).status_code == 204
        assert (await c.delete("/agent/feedback/a1", headers=auth())).status_code == 404
        assert (await c.get("/agent/feedback?conversation_id=conv-1", headers=auth())).json()["feedback"] == []
