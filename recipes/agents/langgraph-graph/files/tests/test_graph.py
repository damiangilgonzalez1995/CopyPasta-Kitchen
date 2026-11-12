"""Graph tests. Need the langchain-agent and agent-memory recipes in the same `agentic/` (and tests/fakes.py)."""

from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage

from agentic.agents import AssistantAgent, ClassifierAgent
from agentic.context import AgentContext
from agentic.conversation import answer_question, stream_answer
from agentic.graph import EventType, ainvoke_graph
from agentic.memory import InMemoryMemory, MemoryKey
from agentic.registry import registry
from agentic.tools import ToolSet

from .fakes import FakeDocumentSearch, ScriptedChatModel, tool_call

CONTEXT = AgentContext(tenant_id="tenant-1", user_id="user-1", language="es")
KEY = MemoryKey(tenant_id="tenant-1", user_id="user-1", conversation_id="conv-1")


def classifier_answering(category: str) -> ClassifierAgent:
    args = {"category": category, "needs_search": True, "confidence": 0.9}
    return ClassifierAgent(llm=ScriptedChatModel(responses=[tool_call("Classification", args, "c_router")]))


class StreamingChatModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> "StreamingChatModel":
        return self


@pytest.fixture(autouse=True)
def clean_registry():
    registry.reset()
    yield
    registry.reset()


async def test_allowed_question_goes_to_agent_with_tools():
    service = FakeDocumentSearch(hits=[{"title": "Factura", "snippet": "IVA 21%"}])
    registry.override(
        classifier=classifier_answering("billing"),
        assistant=AssistantAgent(
            llm=ScriptedChatModel(responses=[tool_call("search_documents", {"query": "iva"}), AIMessage("El IVA es 21%")]),
            tools=ToolSet.default(document_search=service),
        ),
    )

    state = await ainvoke_graph("¿Qué IVA lleva?", context=CONTEXT)

    assert state.blocked is False
    assert state.classification.category == "billing"
    assert state.answer == "El IVA es 21%"
    assert service.calls[0][0] == "tenant-1"
    assert any(isinstance(m, ToolMessage) for m in state.new_messages)


async def test_out_of_scope_question_is_rejected_without_calling_agent():
    registry.override(classifier=classifier_answering("other"))  # no assistant: calling it would fail

    state = await ainvoke_graph("¿Quién ganó la liga?", context=CONTEXT)

    assert state.blocked is True
    assert state.answer.startswith("Solo puedo ayudarte")


async def test_router_failure_fails_open():
    broken = ClassifierAgent(llm=ScriptedChatModel(responses=[AIMessage("x")]))

    async def boom(*args, **kwargs):
        raise RuntimeError("classifier down")

    broken.process = boom
    registry.override(
        classifier=broken,
        assistant=AssistantAgent(llm=ScriptedChatModel(responses=[AIMessage("respuesta")]), tools=[]),
    )

    state = await ainvoke_graph("hola", context=CONTEXT)

    assert state.classification is None
    assert state.answer == "respuesta"


async def test_conversation_persists_and_reuses_history():
    memory = InMemoryMemory()
    registry.override(
        classifier=ClassifierAgent(
            llm=ScriptedChatModel(
                responses=[
                    tool_call("Classification", {"category": "technical", "needs_search": False, "confidence": 1}, "r1"),
                    tool_call("Classification", {"category": "technical", "needs_search": False, "confidence": 1}, "r2"),
                ]
            )
        ),
        assistant=AssistantAgent(llm=ScriptedChatModel(responses=[AIMessage("uno"), AIMessage("dos")]), tools=[]),
    )

    assert (await answer_question("primera", key=KEY, context=CONTEXT, memory=memory)).answer == "uno"
    second = await answer_question("segunda", key=KEY, context=CONTEXT, memory=memory)
    assert second.answer == "dos" and second.conversation_id == "conv-1"

    history = await memory.get_messages(KEY)
    assert [m.content for m in history] == ["primera", "uno", "segunda", "dos"]
    assert await memory.get_messages(KEY, turns=1) == history[2:]
    other_tenant = MemoryKey(tenant_id="tenant-2", user_id="user-1", conversation_id="conv-1")
    assert await memory.get_messages(other_tenant) == []


async def test_stream_emits_routing_tokens_and_done():
    memory = InMemoryMemory()
    registry.override(
        classifier=classifier_answering("technical"),
        assistant=AssistantAgent(llm=StreamingChatModel(messages=iter([AIMessage("hola que tal")])), tools=[]),
    )

    events = [e async for e in stream_answer("hola", key=KEY, context=CONTEXT, memory=memory)]
    types = [e.type for e in events]

    assert types[0] is EventType.ROUTING
    tokens = "".join(e.data["text"] for e in events if e.type is EventType.TOKEN)
    assert tokens == "hola que tal"
    assert types[-1] is EventType.DONE and events[-1].data["answer"] == "hola que tal"
    assert events[-1].data["conversation_id"] == "conv-1"
    assert len(await memory.get_messages(KEY)) == 2


async def test_stream_error_yields_error_event_without_details():
    async def boom(*args, **kwargs):
        raise RuntimeError("secret detail")

    assistant = AssistantAgent(llm=ScriptedChatModel(responses=[AIMessage("x")]), tools=[])
    assistant.process = boom
    registry.override(classifier=classifier_answering("technical"), assistant=assistant)

    events = [e async for e in stream_answer("x", key=KEY, context=CONTEXT, memory=InMemoryMemory())]

    assert events[-1].type is EventType.ERROR
    assert "secret" not in str(events[-1].data)


def test_registry_requires_configuration():
    with pytest.raises(RuntimeError):
        registry._require_configured()
