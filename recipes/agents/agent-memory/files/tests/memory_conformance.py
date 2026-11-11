"""Behaviour every `Memory` backend must have. A new backend = a subclass with a `memory` fixture.

    class TestRedisMemory(MemoryConformance):
        @pytest.fixture
        def memory(self): return RedisMemory(...)
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agentic.memory import MemoryKey

KEY = MemoryKey(tenant_id="tenant-1", user_id="user-1", conversation_id="conv-1")


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
        import pytest

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
