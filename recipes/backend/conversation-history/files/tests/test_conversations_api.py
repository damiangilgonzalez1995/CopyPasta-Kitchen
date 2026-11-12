"""History routes over the app from agent-chat-api with an in-memory `Memory` and a fake clock.
Needs agent-chat-api (and what it requires) copied next to `api/conversations/`."""

import httpx
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agentic.memory import InMemoryMemory, MemoryKey
from api.agent.settings import AgentApiSettings
from api.app import create_app
from api.auth import StaticTokenVerifier
from api.conversations.router import router as conversations_router

from .memory_conformance import FakeClock
from .test_agent_api import TOKENS, auth

ALICE = MemoryKey(tenant_id="tenant-1", user_id="user-1", conversation_id="conv-1")


def make_app(clock: FakeClock | None = None) -> tuple[object, InMemoryMemory]:
    memory = InMemoryMemory(clock=clock or FakeClock())
    app = create_app(
        settings=AgentApiSettings(),
        token_verifier=StaticTokenVerifier(TOKENS),
        memory=memory,
        document_search=None,
    )
    app.include_router(conversations_router)
    return app, memory


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def seed(memory: InMemoryMemory, clock: FakeClock) -> None:
    await memory.add_messages(ALICE, [HumanMessage("¿Qué es RAG?", id="h1"), AIMessage("Retrieval…", id="a1")])
    clock.advance(60)
    await memory.add_messages(
        ALICE.model_copy(update={"conversation_id": "conv-2"}),
        [
            HumanMessage("busca algo", id="h2"),
            AIMessage("", id="call2", tool_calls=[{"name": "search", "args": {}, "id": "t2"}]),
            ToolMessage("resultado", tool_call_id="t2", id="tool2"),
            AIMessage("Encontré esto", id="a2"),
        ],
    )


async def test_routes_need_a_token():
    app, _ = make_app()
    async with client(app) as c:
        assert (await c.get("/conversations")).status_code == 401
        assert (await c.get("/conversations/conv-1/messages")).status_code == 401
        assert (await c.delete("/conversations/conv-1")).status_code == 401


async def test_list_is_newest_first_with_titles_and_pagination():
    clock = FakeClock()
    app, memory = make_app(clock)
    await seed(memory, clock)
    async with client(app) as c:
        body = (await c.get("/conversations", headers=auth())).json()
        page = (await c.get("/conversations?limit=1&offset=1", headers=auth())).json()
        bob = (await c.get("/conversations", headers=auth("tok-bob"))).json()
        bad = await c.get("/conversations?limit=0", headers=auth())

    assert body == {
        "conversations": [
            {
                "conversation_id": "conv-2",
                "title": "busca algo",
                "created_at": "2026-03-30T10:01:00Z",
                "updated_at": "2026-03-30T10:01:00Z",
                "message_count": 4,
            },
            {
                "conversation_id": "conv-1",
                "title": "¿Qué es RAG?",
                "created_at": "2026-03-30T10:00:00Z",
                "updated_at": "2026-03-30T10:00:00Z",
                "message_count": 2,
            },
        ]
    }
    assert [c["conversation_id"] for c in page["conversations"]] == ["conv-1"]
    assert bob == {"conversations": []}
    assert bad.status_code == 422


async def test_messages_show_only_user_and_assistant_text():
    clock = FakeClock()
    app, memory = make_app(clock)
    await seed(memory, clock)
    async with client(app) as c:
        body = (await c.get("/conversations/conv-2/messages", headers=auth())).json()

    assert body == {
        "conversation_id": "conv-2",
        "messages": [
            {"id": "h2", "role": "user", "content": "busca algo", "created_at": "2026-03-30T10:01:00Z"},
            {"id": "a2", "role": "assistant", "content": "Encontré esto", "created_at": "2026-03-30T10:01:00Z"},
        ],
    }


async def test_someone_elses_or_unknown_conversation_is_404():
    clock = FakeClock()
    app, memory = make_app(clock)
    await seed(memory, clock)
    async with client(app) as c:
        assert (await c.get("/conversations/conv-1/messages", headers=auth("tok-bob"))).status_code == 404
        assert (await c.get("/conversations/nope/messages", headers=auth())).status_code == 404
        assert (await c.get("/conversations/bad%20id/messages", headers=auth())).status_code == 422
        assert (await c.delete("/conversations/conv-1", headers=auth("tok-bob"))).status_code == 404
    assert len(await memory.get_history(ALICE)) == 2  # bob's delete did not touch alice's thread


async def test_delete_forgets_the_conversation():
    clock = FakeClock()
    app, memory = make_app(clock)
    await seed(memory, clock)
    async with client(app) as c:
        assert (await c.delete("/conversations/conv-1", headers=auth())).status_code == 204
        assert (await c.get("/conversations/conv-1/messages", headers=auth())).status_code == 404
        remaining = (await c.get("/conversations", headers=auth())).json()["conversations"]

    assert [r["conversation_id"] for r in remaining] == ["conv-2"]
