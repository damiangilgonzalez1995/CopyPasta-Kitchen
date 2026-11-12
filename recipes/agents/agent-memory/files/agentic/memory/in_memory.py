import asyncio
from collections import defaultdict

from langchain_core.messages import BaseMessage

from .base import Memory
from .models import ConversationSummary, HistoryMessage, MemoryKey, title_from


class InMemoryMemory(Memory):
    """Per-process dict. For tests and local dev only: lost on restart, not shared between workers."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._threads: dict[MemoryKey, list[HistoryMessage]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def _fetch_recent_turns(self, key: MemoryKey, turns: int) -> list[BaseMessage]:
        async with self._lock:
            thread = [h.message for h in self._threads.get(key, [])]
        return thread[self.window_start(thread, turns) :]

    async def _append(self, key: MemoryKey, messages: list[BaseMessage]) -> None:
        now = self._clock()
        async with self._lock:
            thread = self._threads[key]
            seen = {h.message.id for h in thread if h.message.id}
            for message in messages:
                if message.id and message.id in seen:
                    continue
                thread.append(HistoryMessage(message=message, created_at=now))
                if message.id:
                    seen.add(message.id)

    async def get_history(self, key: MemoryKey) -> list[HistoryMessage]:
        async with self._lock:
            return list(self._threads.get(key, []))

    async def list_conversations(
        self, tenant_id: str, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[ConversationSummary]:
        async with self._lock:
            mine = {k: v for k, v in self._threads.items() if k.tenant_id == tenant_id and k.user_id == user_id and v}
        summaries = [
            ConversationSummary(
                conversation_id=key.conversation_id,
                title=title_from(next((str(h.message.text) for h in thread if h.message.type == "human"), "")),
                created_at=thread[0].created_at,
                updated_at=thread[-1].created_at,
                message_count=len(thread),
            )
            for key, thread in mine.items()
        ]
        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries[offset : offset + limit]

    async def clear(self, key: MemoryKey) -> None:
        async with self._lock:
            self._threads.pop(key, None)
