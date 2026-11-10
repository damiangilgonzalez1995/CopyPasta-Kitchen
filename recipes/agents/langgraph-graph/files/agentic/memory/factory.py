from enum import Enum
from typing import Any

from .base import Memory


class MemoryBackend(str, Enum):
    IN_MEMORY = "in_memory"
    SQL = "sql"


class MemoryFactory:
    @staticmethod
    def create(backend: MemoryBackend, **options: Any) -> Memory:
        """`SQL` needs `session_factory=`. Unknown backend -> ValueError (no silent default)."""
        match backend:
            case MemoryBackend.IN_MEMORY:
                from .in_memory import InMemoryMemory

                return InMemoryMemory()
            case MemoryBackend.SQL:
                from .sql import SqlMemory

                return SqlMemory(session_factory=options["session_factory"])
        raise ValueError(f"Unknown memory backend: {backend!r}")
