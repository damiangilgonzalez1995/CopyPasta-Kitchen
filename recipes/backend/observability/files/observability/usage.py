"""Tokens per LLM call, provider-independent: a callback that reads `usage_metadata` from every
chat model result (`UsageCollector`), or the same read over persisted messages (`usage_from_messages`).
"""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import LLMResult

from .models import TokenUsage


def usage_of(message: AIMessage) -> TokenUsage | None:
    meta = message.usage_metadata
    if not meta:
        return None
    details = meta.get("input_token_details") or {}
    return TokenUsage(
        model=str((message.response_metadata or {}).get("model_name") or "unknown"),
        input_tokens=int(meta.get("input_tokens", 0)),
        output_tokens=int(meta.get("output_tokens", 0)),
        cached_input_tokens=int(details.get("cache_read", 0) or 0),
    )


def usage_from_messages(messages: Iterable[BaseMessage]) -> list[TokenUsage]:
    """One entry per AI message that carries usage (tool calls included)."""
    return [usage for m in messages if isinstance(m, AIMessage) and (usage := usage_of(m)) is not None]


class UsageCollector(AsyncCallbackHandler):
    """Collects `TokenUsage` of every chat model call of a run. Never raises into the run."""

    raise_error = False
    run_inline = True

    def __init__(self) -> None:
        super().__init__()
        self.usages: list[TokenUsage] = []

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                if isinstance(message, AIMessage) and (usage := usage_of(message)) is not None:
                    self.usages.append(usage)

    @property
    def input_tokens(self) -> int:
        return sum(u.input_tokens for u in self.usages)

    @property
    def output_tokens(self) -> int:
        return sum(u.output_tokens for u in self.usages)

    @property
    def cached_input_tokens(self) -> int:
        return sum(u.cached_input_tokens for u in self.usages)
