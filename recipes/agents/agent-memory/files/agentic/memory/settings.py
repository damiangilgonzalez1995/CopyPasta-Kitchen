"""Memory settings BLOCK, meant to be mixed into the project settings (`project-settings` recipe):

    # core/config.py
    from agentic.memory.settings import MemorySettings

    class Settings(MemorySettings, BaseAppSettings): ...

Env vars: MEMORY_BACKEND (required: in_memory | sql), MEMORY_WINDOW_TURNS (default 10).
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import MemoryBackend


class MemorySettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # No default on purpose: falling back to in-process memory "just in case" turns a config
    # mistake into history silently lost on every restart.
    memory_backend: MemoryBackend
    # How many TURNS are sent back to the LLM. Everything is stored; this only bounds what is read.
    memory_window_turns: int = Field(default=10, ge=1)
