"""Conversation memory contract. Every backend passes the same tests (`tests/memory_conformance.py`).

Not a LangGraph checkpointer: the caller reads a window, runs the agent or graph, and stores
the new messages. That keeps the memory usable by a plain agent too.

- Window in TURNS (a human message plus everything the agent did for it), not in messages:
  the window always starts at a human message, so a tool call is never split from its result
  (providers reject that), and an agent that uses more tools does not remember less.
- Idempotent writes by `message.id`: a message whose id is already in the thread is skipped,
  so a retry never duplicates. Messages without id are always appended; give the human
  message an id from the client (`HumanMessage(text, id=client_message_id)`) to make retries safe.
- Two readers: `get_messages` (the window, for the LLM) and `get_history` (the whole thread
  with timestamps, for the UI). `list_conversations` is the sidebar.
- Async even in memory: the contract follows the slowest backend.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from langchain_core.messages import BaseMessage

from .models import ConversationSummary, HistoryMessage, MemoryKey

DEFAULT_WINDOW_TURNS = 10
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class Memory(ABC):
    def __init__(self, *, window_turns: int = DEFAULT_WINDOW_TURNS, clock: Clock = utc_now) -> None:
        if window_turns < 1:
            raise ValueError(f"`window_turns` must be >= 1, got {window_turns}")
        self.window_turns = window_turns
        self._clock = clock  # stamps `created_at`; tests inject a fake one

    async def get_messages(self, key: MemoryKey, *, turns: int | None = None) -> list[BaseMessage]:
        """Last `turns` turns (default: `window_turns`) in order, ready for the LLM. [] for an unknown thread.

        `turns=0` is a ValueError, not "no limit": it would be an agent with silent amnesia.
        """
        turns = self.window_turns if turns is None else turns
        if turns < 1:
            raise ValueError(f"`turns` must be >= 1, got {turns}")
        return self._start_at_human(await self._fetch_recent_turns(key, turns))

    async def add_messages(self, key: MemoryKey, messages: Sequence[BaseMessage]) -> str | None:
        """Append to the thread (created if needed). Returns the id of the last AI message with
        content (the answer the frontend can vote on), or None."""
        if messages:
            await self._append(key, list(messages))
        return last_answer_id(messages)

    @abstractmethod
    async def get_history(self, key: MemoryKey) -> list[HistoryMessage]:
        """The WHOLE thread in order with timestamps, tool calls included. [] for an unknown thread.
        For the UI; the LLM gets `get_messages`."""

    @abstractmethod
    async def list_conversations(
        self, tenant_id: str, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[ConversationSummary]:
        """The user's conversations, most recently updated first. Title = first human message."""

    @abstractmethod
    async def _fetch_recent_turns(self, key: MemoryKey, turns: int) -> list[BaseMessage]:
        """From the `turns`-th human message counting from the end, to the end. Whole thread if shorter."""

    @abstractmethod
    async def _append(self, key: MemoryKey, messages: list[BaseMessage]) -> None:
        """Store `messages` in order with `created_at = self._clock()`, skipping any whose `id` is
        already in the thread."""

    @abstractmethod
    async def clear(self, key: MemoryKey) -> None:
        """Delete the thread (user asks to forget it). Unknown thread: no-op."""

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


def last_answer_id(messages: Sequence[BaseMessage]) -> str | None:
    """Id of the last AI message with text. Empty AI messages are tool calls, not answers."""
    for message in reversed(messages):
        if message.type == "ai" and str(message.text).strip():
            return message.id
    return None
