"""Base of every agent: a thin, testable wrapper around `langchain.agents.create_agent`.

Life cycle: `__init__` (cheap, no I/O) -> `await initialize()` (builds `self.agent` once)
-> `await process(...)` (one turn). `process` calls `initialize` itself, so callers may skip it.

A subclass declares:
- `agent_type` (class attribute)
- `response_format` (class attribute, optional): a Pydantic model -> `AgentTurn.structured`;
  None -> plain text in `AgentTurn.answer`.
- `get_prompt()`: the system prompt (usually `load_prompt(...).render(...)`).
- `get_tools()` / `get_middleware()`: optional, empty by default.

The model is chosen FROM OUTSIDE (`model`, usually `LLMModel.from_id(settings.<agent>_model)`),
never hard-coded in the class. Credentials come from the project settings via `get_llm_settings()`;
`settings=` is only for tests.
`llm=` is the test seam: pass a fake chat model and nothing else is built.

The agent is stateless: it receives the history and returns the new messages. Persisting
them is the caller's job (see the langgraph-graph recipe, `memory/`).
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from ..context import AgentContext
from ..llm.models import LLMModel
from ..llm.provider import LLMProvider
from ..llm.settings import LLMSettings
from .models import AgentError, AgentTurn, AgentType

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    agent_type: ClassVar[AgentType]
    response_format: ClassVar[type[BaseModel] | None] = None
    context_schema: ClassVar[type[BaseModel]] = AgentContext

    def __init__(
        self,
        model: LLMModel | None = None,
        settings: LLMSettings | None = None,
        *,
        language: str = "es",
        temperature: float | None = 0.0,
        streaming: bool = False,
        llm: BaseChatModel | None = None,
    ) -> None:
        if llm is None:
            if model is None:
                raise ValueError(f"{type(self).__name__} needs a `model` (or an `llm` in tests)")
            llm = LLMProvider.create_from_model(model, settings, temperature=temperature, streaming=streaming)
        self.model = model
        self.language = language
        self.llm = llm
        self.agent: Any = None

    # --- What a subclass defines ---------------------------------------------------------------

    @abstractmethod
    def get_prompt(self) -> str:
        """The system prompt of this agent."""

    def get_tools(self) -> Sequence[BaseTool]:
        return []

    def get_middleware(self) -> Sequence[AgentMiddleware]:
        return []

    # --- Template -----------------------------------------------------------------------------

    async def initialize(self) -> None:
        """Build the LangChain agent once. A second call is a no-op."""
        if self.agent is not None:
            return
        self.agent = create_agent(
            model=self.llm,
            tools=list(self.get_tools()),
            system_prompt=self.get_prompt(),
            middleware=list(self.get_middleware()),
            response_format=self.response_format,
            context_schema=self.context_schema,
            name=self.agent_type.value,
        )
        logger.info("Agent %s ready (model=%s)", self.agent_type.value, getattr(self.model, "model_id", "injected"))

    def build_messages(self, question: str, history: Sequence[BaseMessage]) -> list[BaseMessage]:
        """Input messages of one turn. Override to add images, XML-tagged data, etc."""
        return [*history, HumanMessage(question)]

    async def process(
        self,
        question: str,
        *,
        context: AgentContext,
        history: Sequence[BaseMessage] = (),
        config: RunnableConfig | None = None,
    ) -> AgentTurn:
        """Run one turn. `config` carries callbacks/metadata (observability), never business data."""
        await self.initialize()
        previous = list(history)
        result = await self.agent.ainvoke(
            {"messages": self.build_messages(question, previous)}, context=context, config=config
        )
        return self._to_turn(result, len(previous))

    def _to_turn(self, result: dict[str, Any], history_len: int) -> AgentTurn:
        messages: list[BaseMessage] = result.get("messages") or []
        if not messages:
            raise AgentError("the agent produced no messages", kind="NoMessages")
        structured = result.get("structured_response")
        if self.response_format is not None and structured is None:
            raise AgentError("the agent ended without a structured answer", kind="NoStructuredResponse")
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        answer = str(last_ai.text) if last_ai is not None else ""
        return AgentTurn(answer=answer, structured=structured, new_messages=messages[history_len:])
