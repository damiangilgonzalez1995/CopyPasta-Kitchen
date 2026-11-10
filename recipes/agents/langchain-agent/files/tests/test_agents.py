import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agentic.agents import AgentError, AssistantAgent, ClassifierAgent, Classification
from agentic.context import AgentContext
from agentic.llm import LLMModel, LLMProvider, LLMSettings
from agentic.prompts import load_prompt
from agentic.tools import AppTool, ToolSet

from .fakes import FakeDocumentSearch, ScriptedChatModel, tool_call

CONTEXT = AgentContext(tenant_id="tenant-1", user_id="user-1", language="es")


async def test_assistant_uses_tool_with_tenant_from_context():
    service = FakeDocumentSearch(hits=[{"title": "Guía", "snippet": "texto"}])
    llm = ScriptedChatModel(
        responses=[tool_call("search_documents", {"query": "vacaciones"}), AIMessage("Según la Guía...")]
    )
    agent = AssistantAgent(llm=llm, tools=ToolSet.default(document_search=service))

    turn = await agent.process("¿Cuántos días de vacaciones?", context=CONTEXT)

    assert turn.answer == "Según la Guía..."
    assert turn.structured is None
    assert service.calls == [("tenant-1", "vacaciones", 5)]
    tool_messages = [m for m in turn.new_messages if isinstance(m, ToolMessage)]
    assert tool_messages[0].content == "Guía: texto"


async def test_new_messages_exclude_history():
    llm = ScriptedChatModel(responses=[AIMessage("hola de nuevo")])
    agent = AssistantAgent(llm=llm, tools=[])
    history = [HumanMessage("hola"), AIMessage("hola")]

    turn = await agent.process("¿sigues ahí?", context=CONTEXT, history=history)

    assert [type(m) for m in turn.new_messages] == [HumanMessage, AIMessage]


def test_llm_never_sees_runtime_argument():
    tool = ToolSet.default(document_search=FakeDocumentSearch())[0]
    assert set(tool.tool_call_schema.model_json_schema()["properties"]) == {"query", "limit"}


async def test_tool_failure_returns_safe_message():
    service = FakeDocumentSearch(error=RuntimeError("password=secret"))
    llm = ScriptedChatModel(responses=[tool_call("search_documents", {"query": "x"}), AIMessage("fin")])
    agent = AssistantAgent(llm=llm, tools=ToolSet.default(document_search=service))

    turn = await agent.process("x", context=CONTEXT)

    tool_message = next(m for m in turn.new_messages if isinstance(m, ToolMessage))
    assert tool_message.content == AppTool.SAFE_FAILURE
    assert "secret" not in tool_message.content


async def test_classifier_returns_structured_answer():
    args = {"category": "billing", "needs_search": False, "confidence": 0.9}
    llm = ScriptedChatModel(responses=[tool_call("Classification", args)])
    agent = ClassifierAgent(llm=llm)

    turn = await agent.process("¿Por qué me cobrasteis dos veces?", context=CONTEXT)

    assert turn.structured == Classification(**args)


def test_missing_structured_answer_raises():
    # create_agent keeps asking the model until it calls the structured-output tool, so a run
    # that ends without it means a limit cut it short: the agent must not return a half answer.
    agent = ClassifierAgent(llm=ScriptedChatModel(responses=[AIMessage("x")]))

    with pytest.raises(AgentError) as error:
        agent._to_turn({"messages": [HumanMessage("x"), AIMessage("no sé")]}, history_len=0)
    assert error.value.kind == "NoStructuredResponse"


async def test_initialize_is_idempotent():
    agent = AssistantAgent(llm=ScriptedChatModel(responses=[AIMessage("a")]), tools=[])
    await agent.initialize()
    first = agent.agent
    await agent.initialize()
    assert agent.agent is first


def test_agent_requires_model_and_settings_or_llm():
    with pytest.raises(ValueError):
        AssistantAgent(tools=[])


def test_prompt_falls_back_to_default_language():
    assert load_prompt("assistant", "fr").language == "es"


def test_prompt_rejects_path_traversal():
    with pytest.raises(ValueError):
        load_prompt("../secrets")


@pytest.mark.parametrize(
    "model, settings",
    [
        (LLMModel.GPT_4_1_MINI, LLMSettings(openai_api_key="k")),
        (LLMModel.CLAUDE_HAIKU_5_5, LLMSettings(anthropic_api_key="k")),
        (LLMModel.LLAMA_3_3_70B, LLMSettings(groq_api_key="k")),
        (
            LLMModel.AZURE_GPT_4_1,
            LLMSettings(
                azure_openai_api_key="k",
                azure_openai_endpoint="https://example.openai.azure.com",
                azure_openai_api_version="2024-10-21",
            ),
        ),
    ],
)
def test_factory_builds_every_provider(model, settings):
    llm = LLMProvider.create_from_model(model, settings, temperature=0)
    assert llm is not None


def test_factory_fails_without_key():
    with pytest.raises(ValueError):
        LLMProvider.create_from_model(LLMModel.GPT_4_1, LLMSettings())


def test_model_from_id():
    assert LLMModel.from_id("gpt-4.1-nano") is LLMModel.GPT_4_1_NANO
    with pytest.raises(ValueError):
        LLMModel.from_id("nope")
