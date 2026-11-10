"""Tool registry: adding a tool = one file + one line in `ToolSet.default`."""

from collections.abc import Sequence
from typing import Any

from langchain_core.tools import BaseTool

from .base_tool import AppTool, ToolContextError
from .search_documents import SearchDocumentsTool


class ToolSet:
    @staticmethod
    def default(*, document_search: Any) -> list[BaseTool]:
        """The tools of the main agent, built with the services they need."""
        return [
            SearchDocumentsTool(service=document_search),
        ]

    @staticmethod
    def names(tools: Sequence[BaseTool]) -> list[str]:
        return [tool.name for tool in tools]


__all__ = ["AppTool", "SearchDocumentsTool", "ToolContextError", "ToolSet"]
