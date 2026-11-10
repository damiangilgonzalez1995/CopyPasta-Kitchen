"""Example tool. Copy this file to add a tool, then register it in `tools/__init__.py`."""

from typing import Any, Protocol

from langchain.tools import ToolRuntime
from pydantic import BaseModel, ConfigDict, Field

from ..context import AgentContext
from .base_tool import AppTool


class DocumentSearch(Protocol):
    """What the tool needs from the app. The real service is injected; tests pass a fake."""

    async def search(self, tenant_id: str, query: str, limit: int) -> list[dict[str, Any]]: ...


class SearchDocumentsArgs(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    query: str = Field(description="What to look for, rewritten as a short search query.")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of documents to return.")
    runtime: ToolRuntime[AgentContext]  # injected, hidden from the LLM


class SearchDocumentsTool(AppTool):
    name: str = "search_documents"
    description: str = (
        "Search the user's documents. Use it whenever the answer depends on them. "
        "Returns one line per document: '<title>: <snippet>', or 'No results.'"
    )
    args_schema: type[BaseModel] = SearchDocumentsArgs

    service: Any = Field(exclude=True)  # DocumentSearch

    async def execute(self, runtime: ToolRuntime, *, query: str, limit: int = 5) -> str:
        context = self.context_of(runtime)  # tenant comes from the context, never from the LLM
        self.emit(runtime, {"tool": self.name, "status": "searching", "query": query})
        hits = await self.service.search(context.tenant_id, query, limit)
        if not hits:
            return "No results."
        return "\n".join(f"{hit['title']}: {hit['snippet']}" for hit in hits)
