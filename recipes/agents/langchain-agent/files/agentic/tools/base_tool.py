"""Base for every tool of the app.

A tool subclass declares:
- `name`: snake_case verb (`search_documents`, `get_order`).
- `description`: explicit string, not a docstring. Says WHEN to use it and WHAT it returns.
  It is all the LLM knows about the tool.
- `args_schema`: Pydantic model with `Field(description=...)` per argument, plus a
  `runtime: ToolRuntime` field. `runtime` is injected by LangChain and hidden from the LLM.
- `execute(runtime, **args)`: the async work. Return a string (what the LLM reads).

The base gives:
- `_arun` with fail-safe errors: an exception is logged and the LLM gets SAFE_FAILURE,
  never the internal message (it could leak keys, SQL, paths...).
- `context_of(runtime)`: the AgentContext, fail-closed if it is missing.
- `emit(runtime, data)`: custom stream event (shows up in `stream_mode="custom"`).
"""

import logging
from abc import abstractmethod
from typing import Any, ClassVar

from langchain.tools import BaseTool, ToolRuntime

from ..context import AgentContext

logger = logging.getLogger(__name__)


class ToolContextError(RuntimeError):
    """The tool ran without an AgentContext: a wiring bug. Never answer without a tenant."""


class AppTool(BaseTool):
    SAFE_FAILURE: ClassVar[str] = "The tool failed. Do not retry it; answer with what you already have."

    @abstractmethod
    async def execute(self, runtime: ToolRuntime, **kwargs: Any) -> str:
        """The work of the tool. Raise freely: `_arun` turns errors into SAFE_FAILURE."""

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError(f"{self.name} is async only; run the agent with ainvoke/astream")

    async def _arun(self, *args: Any, runtime: ToolRuntime, **kwargs: Any) -> str:
        try:
            return await self.execute(runtime, **kwargs)
        except ToolContextError:
            raise
        except Exception:
            logger.exception("Tool %s failed", self.name)
            return self.SAFE_FAILURE

    @staticmethod
    def context_of(runtime: ToolRuntime) -> AgentContext:
        context = getattr(runtime, "context", None)
        if not isinstance(context, AgentContext):
            raise ToolContextError("Tool called without AgentContext (pass context= to the agent run)")
        return context

    @staticmethod
    def emit(runtime: ToolRuntime, data: dict[str, Any]) -> None:
        if runtime.stream_writer is not None:
            runtime.stream_writer(data)
