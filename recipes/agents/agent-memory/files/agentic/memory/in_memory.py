import asyncio
from collections import defaultdict

from langchain_core.messages import BaseMessage

from .base import Memory
from .models import MemoryKey


class InMemoryMemory(Memory):
    """Per-process dict. For tests and local dev only: lost on restart, not shared between workers."""

    def __init__(self, *, window_turns: int = 10) -> None:
        super().__init__(window_turns=window_turns)
        self._threads: dict[MemoryKey, list[BaseMessage]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def _fetch_recent_turns(self, key: MemoryKey, turns: int) -> list[BaseMessage]:
        async with self._lock:
            thread = list(self._threads.get(key, []))
        return thread[self.window_start(thread, turns) :]

    async def _append(self, key: MemoryKey, messages: list[BaseMessage]) -> None:
        async with self._lock:
            thread = self._threads[key]
            seen = {m.id for m in thread if m.id}
            for message in messages:
                if message.id and message.id in seen:
                    continue
                thread.append(message)
                if message.id:
                    seen.add(message.id)

    async def clear(self, key: MemoryKey) -> None:
        async with self._lock:
            self._threads.pop(key, None)
