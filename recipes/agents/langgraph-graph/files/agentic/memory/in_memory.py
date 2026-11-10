import asyncio
from collections import defaultdict
from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from .base import Memory
from .models import MemoryKey


class InMemoryMemory(Memory):
    """Per-process dict. For tests and local dev only: lost on restart, not shared between workers."""

    def __init__(self) -> None:
        self._threads: dict[MemoryKey, list[BaseMessage]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def _fetch_recent_turns(self, key: MemoryKey, turns: int) -> list[BaseMessage]:
        async with self._lock:
            thread = list(self._threads.get(key, []))
        return thread[self.window_start(thread, turns) :]

    async def add_messages(self, key: MemoryKey, messages: Sequence[BaseMessage]) -> None:
        async with self._lock:
            self._threads[key].extend(messages)
