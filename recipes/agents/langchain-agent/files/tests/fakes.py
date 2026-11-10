"""Test doubles: a scripted chat model and a fake document service. No API keys needed."""

from typing import Any

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage


class ScriptedChatModel(FakeMessagesListChatModel):
    """Returns the given AIMessages in order. `bind_tools` is a no-op so it works inside create_agent."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self


def tool_call(name: str, args: dict[str, Any], call_id: str = "call_1") -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": call_id}])


class FakeDocumentSearch:
    def __init__(self, hits: list[dict[str, Any]] | None = None, error: Exception | None = None) -> None:
        self.hits = hits or []
        self.error = error
        self.calls: list[tuple[str, str, int]] = []

    async def search(self, tenant_id: str, query: str, limit: int) -> list[dict[str, Any]]:
        self.calls.append((tenant_id, query, limit))
        if self.error:
            raise self.error
        return self.hits
