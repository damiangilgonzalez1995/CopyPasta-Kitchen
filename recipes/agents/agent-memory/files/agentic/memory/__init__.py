"""Conversation memory for agents. Independent: used by a plain agent or by a graph.

Backend chosen in the settings (`MEMORY_BACKEND`), built by `MemoryFactory`. Nothing here imports the app.
"""

from .base import DEFAULT_WINDOW_TURNS, Memory, last_answer_id
from .factory import MemoryFactory
from .in_memory import InMemoryMemory
from .models import TITLE_MAX_LENGTH, ConversationSummary, HistoryMessage, MemoryBackend, MemoryKey, title_from
from .settings import MemorySettings

__all__ = [
    "DEFAULT_WINDOW_TURNS",
    "ConversationSummary",
    "HistoryMessage",
    "InMemoryMemory",
    "Memory",
    "MemoryBackend",
    "MemoryFactory",
    "MemoryKey",
    "MemorySettings",
    "TITLE_MAX_LENGTH",
    "last_answer_id",
    "title_from",
]
