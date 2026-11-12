"""Chat endpoints over the real graph with fake LLMs. Needs langgraph-graph (and what it requires)
copied next to `api/`, plus tests/fakes.py from langchain-agent."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from langchain_core.messages import AIMessage

from agentic.agents import AssistantAgent, ClassifierAgent
from agentic.memory import InMemoryMemory, MemoryKey
from agentic.registry import registry
from api.agent.guards import ensure_turn_allowed
from api.agent.settings import AgentApiSettings
from api.app import create_app
from api.auth import CurrentUser, StaticTokenVerifier
from fastapi import HTTPException

from .fakes import ScriptedChatModel, tool_call
from .test_graph import StreamingChatModel

ALICE = CurrentUser(id="user-1", tenant_id="tenant-1")
BOB = CurrentUser(id="user-2", tenant_id="tenant-2", language="en")
TOKENS = {"tok-alice": ALICE, "tok-bob": BOB}


def classifier_answering(category: str) -> ClassifierAgent:
    args = {"category": category, "needs_search": False, "confidence": 0.9}
    return ClassifierAgent(llm=ScriptedChatModel(responses=[tool_call("Classification", args, "c_router")]))


def make_app(memory: InMemoryMemory | None = None, **settings) -> tuple[object, InMemoryMemory]:
    memory = memory or InMemoryMemory()
    app = create_app(
        settings=AgentApiSettings(**settings),
        token_verifier=StaticTokenVerifier(TOKENS),
        memory=memory,
        document_search=None,
    )
    return app, memory


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def auth(token: str = "tok-alice") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def sse_events(response: httpx.Response) -> list[tuple[str, dict]]:
    """Minimal SSE reader for tests: (event, parsed data) per block."""
    events, event, data = [], None, []
    async for line in response.aiter_lines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())
        elif line == "" and event is not None:
            events.append((event, json.loads("\n".join(data))))
            event, data = None, []
    return events


@pytest.fixture(autouse=True)
def answering_agents():
    registry.reset()
    registry.override(
        classifier=classifier_answering("technical"),
        assistant=AssistantAgent(llm=ScriptedChatModel(responses=[AIMessage("uno"), AIMessage("dos")]), tools=[]),
    )
    yield
    registry.reset()


async def test_without_token_is_401_and_with_unknown_token_too():
    app, _ = make_app()
    async with client(app) as c:
        assert (await c.post("/agent/chat", json={"question": "hola"})).status_code == 401
        assert (await c.post("/agent/chat", json={"question": "hola"}, headers=auth("nope"))).status_code == 401


async def test_disabled_endpoint_is_404_even_without_token():
    app, _ = make_app(agent_endpoint_enabled=False)
    async with client(app) as c:
        assert (await c.post("/agent/chat", json={"question": "hola"})).status_code == 404
        assert (await c.post("/agent/stream", json={"question": "hola"}, headers=auth())).status_code == 404


async def test_blank_or_too_long_question_is_400():
    app, _ = make_app(chat_max_question_length=10)
    async with client(app) as c:
        assert (await c.post("/agent/chat", json={"question": "  <b> </b> "}, headers=auth())).status_code == 400
        assert (await c.post("/agent/chat", json={"question": "x" * 11}, headers=auth())).status_code == 400
        assert (await c.post("/agent/chat", json={"question": ""}, headers=auth())).status_code == 422


async def test_chat_answers_and_server_generates_the_conversation_id():
    app, memory = make_app()
    async with client(app) as c:
        response = await c.post("/agent/chat", json={"question": "hola"}, headers=auth())

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "uno"
    assert body["message_id"]  # the persisted answer, votable
    key = MemoryKey(tenant_id="tenant-1", user_id="user-1", conversation_id=body["conversation_id"])
    assert [m.content for m in await memory.get_messages(key)] == ["hola", "uno"]


async def test_same_conversation_id_continues_the_thread_and_tenants_do_not_mix():
    app, memory = make_app()
    async with client(app) as c:
        await c.post("/agent/chat", json={"question": "primera", "conversation_id": "conv-1"}, headers=auth())
        second = await c.post("/agent/chat", json={"question": "segunda", "conversation_id": "conv-1"}, headers=auth())

    assert second.json() == {"answer": "dos", "conversation_id": "conv-1", "message_id": second.json()["message_id"]}
    alice = MemoryKey(tenant_id="tenant-1", user_id="user-1", conversation_id="conv-1")
    assert [m.content for m in await memory.get_messages(alice)] == ["primera", "uno", "segunda", "dos"]
    bob_same_id = MemoryKey(tenant_id="tenant-2", user_id="user-2", conversation_id="conv-1")
    assert await memory.get_messages(bob_same_id) == []


async def test_turn_guard_can_refuse_before_anything_runs():
    app, memory = make_app()

    async def quota_exhausted() -> CurrentUser:
        raise HTTPException(429, {"code": "ai_quota_daily_exhausted"})

    app.dependency_overrides[ensure_turn_allowed] = quota_exhausted
    async with client(app) as c:
        response = await c.post("/agent/stream", json={"question": "hola"}, headers=auth())

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "ai_quota_daily_exhausted"
    assert await memory.get_messages(MemoryKey(tenant_id="tenant-1", user_id="user-1", conversation_id="x")) == []


async def test_stream_sends_tokens_and_done_with_ids():
    registry.override(assistant=AssistantAgent(llm=StreamingChatModel(messages=iter([AIMessage("hola que tal")])), tools=[]))
    app, _ = make_app()
    async with client(app) as c:
        async with c.stream("POST", "/agent/stream", json={"question": "hola", "conversation_id": "conv-9"}, headers=auth()) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            events = await sse_events(r)

    names = [name for name, _ in events]
    assert names[0] == "routing" and names[-1] == "done"
    assert "".join(d["text"] for n, d in events if n == "token") == "hola que tal"
    done = events[-1][1]
    assert done["answer"] == "hola que tal" and done["conversation_id"] == "conv-9" and done["message_id"]


async def test_stream_failure_outside_the_graph_becomes_an_error_event_with_id_only():
    class BrokenMemory(InMemoryMemory):
        async def get_messages(self, key, turns=None):  # type: ignore[override]
            raise RuntimeError("db password is hunter2")

    app, _ = make_app(memory=BrokenMemory())
    async with client(app) as c:
        async with c.stream("POST", "/agent/stream", json={"question": "hola"}, headers=auth()) as r:
            assert r.status_code == 200
            events = await sse_events(r)

    assert [name for name, _ in events] == ["error"]
    assert set(events[0][1]) == {"error_id"}
    assert "hunter2" not in json.dumps(events)


async def test_language_comes_from_body_then_from_user():
    seen: list[str] = []

    class SpyAssistant(AssistantAgent):
        async def process(self, question, *, context, history=(), config=None):  # type: ignore[override]
            seen.append(context.language)
            return await super().process(question, context=context, history=history, config=config)

    spy = SpyAssistant(llm=ScriptedChatModel(responses=[AIMessage("a"), AIMessage("b")]), tools=[])
    for language in ("fr", "en"):  # the registry keeps one assistant per language
        registry.override(assistant=spy, language=language)
    app, _ = make_app()
    async with client(app) as c:
        await c.post("/agent/chat", json={"question": "hi", "language": "fr"}, headers=auth("tok-bob"))
        await c.post("/agent/chat", json={"question": "hi"}, headers=auth("tok-bob"))

    assert seen == ["fr", "en"]


async def test_docs_hidden_by_default():
    app, _ = make_app()
    async with client(app) as c:
        assert (await c.get("/docs")).status_code == 404
