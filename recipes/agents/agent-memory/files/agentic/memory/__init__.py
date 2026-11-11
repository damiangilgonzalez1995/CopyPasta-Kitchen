"""Conversation memory for agents. Independent: used by a plain agent or by a graph.

Backend chosen in the settings (`MEMORY_BACKEND`), built by `MemoryFactory`. Nothing here imports the app.
"""

from .base import DEFAULT_WINDOW_TURNS, Memory, last_answer_id
from .factory import MemoryFactory
from .in_memory import InMemoryMemory
from .models import MemoryBackend, MemoryKey
from .settings import MemorySettings

__all__ = [
    "DEFAULT_WINDOW_TURNS",
    "InMemoryMemory",
    "Memory",
    "MemoryBackend",
    "MemoryFactory",
    "MemoryKey",
    "MemorySettings",
    "last_answer_id",
]
