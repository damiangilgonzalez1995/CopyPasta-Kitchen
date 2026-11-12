"""Behaviour every `Memory` backend must have. A new backend = a subclass with a `memory` fixture.

    class TestRedisMemory(MemoryConformance):
        @pytest.fixture
        def memory(self, clock): return RedisMemory(..., clock=clock)

`clock` is a `FakeClock` (starts at START): tests move time with `clock.advance(seconds)`.
"""

from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agentic.memory import MemoryKey

KEY = MemoryKey(tenant_id="tenant-1", user_id="user-1", conversation_id="conv-1")
START = datetime(2026, 3, 30, 10, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def turn(n: int, *, with_tool: bool = False) -> list:
    messages = [HumanMessage(f"q{n}", id=f"h{n}")]
    if with_tool:
        messages += [
            AIMessage("", id=f"call{n}", tool_calls=[{"name": "search", "args": {"q": n}, "id": f"t{n}"}]),
            ToolMessage("ok", tool_call_id=f"t{n}", id=f"tool{n}"),
        ]
    return messages + [AIMessage(f"a{n}", id=f"a{n}")]


def texts(messages) -> list[str]:
    return [m.content for m in messages]


class MemoryConformance:
    async def test_unknown_thread_is_empty(self, memory):
        assert await memory.get_messages(KEY) == []

    async def test_round_trip_keeps_order_and_tool_calls(self, memory):
        await memory.add_messages(KEY, turn(1, with_tool=True))

        got = await memory.get_messages(KEY)

        assert got == turn(1, with_tool=True)
        assert got[1].tool_calls[0]["id"] == "t1"
        assert got[2].tool_call_id == "t1"

    async def test_window_counts_turns_and_never_splits_a_tool(self, memory):
        await memory.add_messages(KEY, turn(1))
        await memory.add_messages(KEY, turn(2, with_tool=True))
        await memory.add_messages(KEY, turn(3))

        last_two = await memory.get_messages(KEY, turns=2)

        assert texts(last_two)[0] == "q2"  # starts at a human message, tool call and result together
        assert len(last_two) == 4 + 2

    async def test_default_window_comes_from_settings(self, memory):
        for n in range(1, memory.window_turns + 3):
            await memory.add_messages(KEY, turn(n))
        got = await memory.get_messages(KEY)
        assert sum(m.type == "human" for m in got) == memory.window_turns

    async def test_zero_turns_is_an_error(self, memory):
        with pytest.raises(ValueError):
            await memory.get_messages(KEY, turns=0)

    async def test_threads_are_isolated_by_tenant_and_user(self, memory):
        await memory.add_messages(KEY, turn(1))
        other_tenant = MemoryKey(tenant_id="tenant-2", user_id="user-1", conversation_id="conv-1")
        other_user = MemoryKey(tenant_id="tenant-1", user_id="user-2", conversation_id="conv-1")
        assert await memory.get_messages(other_tenant) == []
        assert await memory.get_messages(other_user) == []

    async def test_retry_with_same_ids_does_not_duplicate(self, memory):
        await memory.add_messages(KEY, turn(1, with_tool=True))
        await memory.add_messages(KEY, turn(1, with_tool=True))

        assert len(await memory.get_messages(KEY)) == 4

    async def test_messages_without_id_are_always_appended(self, memory):
        await memory.add_messages(KEY, [HumanMessage("hola"), AIMessage("hey")])
        await memory.add_messages(KEY, [HumanMessage("hola"), AIMessage("hey")])
        assert texts(await memory.get_messages(KEY)) == ["hola", "hey", "hola", "hey"]

    async def test_add_returns_the_answer_id(self, memory):
        assert await memory.add_messages(KEY, turn(1, with_tool=True)) == "a1"
        assert await memory.add_messages(KEY, [HumanMessage("x", id="hx")]) is None

    async def test_clear_forgets_only_that_thread(self, memory):
        other = MemoryKey(tenant_id="tenant-1", user_id="user-1", conversation_id="conv-2")
        await memory.add_messages(KEY, turn(1))
        await memory.add_messages(other, turn(1))

        await memory.clear(KEY)

        assert await memory.get_messages(KEY) == []
        assert len(await memory.get_messages(other)) == 2

    # --- History and conversation list (what `conversation-history` exposes) -------------------

    async def test_history_is_the_whole_thread_with_timestamps(self, memory, clock):
        await memory.add_messages(KEY, turn(1, with_tool=True))
        clock.advance(60)
        await memory.add_messages(KEY, turn(2))

        history = await memory.get_history(KEY)

        assert [h.message for h in history] == turn(1, with_tool=True) + turn(2)
        assert [h.created_at for h in history] == [START] * 4 + [START + timedelta(seconds=60)] * 2
        assert await memory.get_history(KEY.model_copy(update={"conversation_id": "nope"})) == []

    async def test_list_is_newest_first_with_title_and_counts(self, memory, clock):
        older = MemoryKey(tenant_id="tenant-1", user_id="user-1", conversation_id="conv-old")
        await memory.add_messages(older, [HumanMessage("  Una   pregunta muy larga " + "x" * 80, id="h0"), AIMessage("a", id="a0")])
        clock.advance(60)
        await memory.add_messages(KEY, turn(1, with_tool=True))
        clock.advance(60)
        await memory.add_messages(older, turn(9))  # activity: `older` is now the most recent

        conversations = await memory.list_conversations("tenant-1", "user-1")

        assert [c.conversation_id for c in conversations] == ["conv-old", "conv-1"]
        old, new = conversations
        assert old.title == "Una pregunta muy larga " + "x" * 36 + "…" and len(old.title) == 60
        assert (old.created_at, old.updated_at, old.message_count) == (START, START + timedelta(seconds=120), 4)
        assert (new.title, new.message_count) == ("q1", 4)

    async def test_list_is_paginated_and_isolated_by_tenant_and_user(self, memory, clock):
        for n in range(3):
            await memory.add_messages(KEY.model_copy(update={"conversation_id": f"c{n}"}), turn(n))
            clock.advance(1)
        await memory.add_messages(MemoryKey(tenant_id="tenant-2", user_id="user-1", conversation_id="c9"), turn(9))

        assert [c.conversation_id for c in await memory.list_conversations("tenant-1", "user-1", limit=2)] == ["c2", "c1"]
        assert [c.conversation_id for c in await memory.list_conversations("tenant-1", "user-1", limit=2, offset=2)] == ["c0"]
        assert await memory.list_conversations("tenant-1", "user-2") == []

    async def test_clear_removes_it_from_the_list(self, memory):
        await memory.add_messages(KEY, turn(1))
        await memory.clear(KEY)
        assert await memory.list_conversations("tenant-1", "user-1") == []
