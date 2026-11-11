"""The one place that builds the memory from the backend the settings name. There is no default."""

from collections.abc import Callable
from typing import Any

from .base import Memory
from .models import MemoryBackend
from .settings import MemorySettings


class MemoryFactory:
    @staticmethod
    def create(settings: MemorySettings, *, session_factory: Callable[[], Any] | None = None) -> Memory:
        """Build the backend in `settings.memory_backend` with `settings.memory_window_turns`.

        Call it once at startup (FastAPI `lifespan`) with the project settings:
            memory = MemoryFactory.create(get_settings(), session_factory=SessionLocal)

        `SQL` needs the app's `session_factory`. Unknown backend -> ValueError.
        """
        window = settings.memory_window_turns
        match settings.memory_backend:
            case MemoryBackend.IN_MEMORY:
                from .in_memory import InMemoryMemory

                return InMemoryMemory(window_turns=window)
            case MemoryBackend.SQL:
                if session_factory is None:
                    raise ValueError("MEMORY_BACKEND=sql needs the app's session_factory")
                from .sql import SqlMemory

                return SqlMemory(session_factory, window_turns=window)
        raise ValueError(f"Unknown memory backend: {settings.memory_backend!r}")
