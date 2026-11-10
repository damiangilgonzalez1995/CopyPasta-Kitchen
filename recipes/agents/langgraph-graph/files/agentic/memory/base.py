"""Conversation memory contract.

The graph is compiled WITHOUT a checkpointer: memory is ours. Each turn the caller reads a
window of history, passes it into the graph, and persists the new messages afterwards.

The window is counted in TURNS (a human message plus everything the agent did for it), not in
messages. That way the window always starts at a human message and never splits a tool call
from its result, which providers reject.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from .models import MemoryKey

DEFAULT_HISTORY_TURNS = 10


class Memory(ABC):
    """Public methods are async even for in-memory: the contract follows the slowest backend."""

    async def get_messages(self, key: MemoryKey, *, turns: int = DEFAULT_HISTORY_TURNS) -> list[BaseMessage]:
        """Last `turns` turns of the thread in order, or [] if it does not exist."""
        if turns < 1:
            raise ValueError(f"`turns` must be >= 1, got {turns}")
        return self._start_at_human(await self._fetch_recent_turns(key, turns))

    @abstractmethod
    async def _fetch_recent_turns(self, key: MemoryKey, turns: int) -> list[BaseMessage]:
        """From the `turns`-th human message counting from the end, to the end."""

    @abstractmethod
    async def add_messages(self, key: MemoryKey, messages: Sequence[BaseMessage]) -> None:
        """Append messages to the thread, creating it if needed."""

    @staticmethod
    def _start_at_human(messages: list[BaseMessage]) -> list[BaseMessage]:
        """Safety net: drop any prefix before the first human message."""
        for index, message in enumerate(messages):
            if message.type == "human":
                return messages[index:]
        return []

    @staticmethod
    def window_start(messages: Sequence[BaseMessage], turns: int) -> int:
        """Index where the last `turns` turns begin (0 if there are fewer)."""
        humans = [i for i, m in enumerate(messages) if m.type == "human"]
        return humans[-turns] if len(humans) >= turns else 0
