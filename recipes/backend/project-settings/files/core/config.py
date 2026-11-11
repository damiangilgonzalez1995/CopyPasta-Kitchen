"""Project settings: ONE object for the whole backend, loaded from env vars / `.env`.

Lives at the backend root (next to `api/`, `db/`, `agentic/`...). Everyone reads it through
`get_settings()`; nobody calls `os.environ` directly.

Composition: each module that needs config brings its own block (a `BaseSettings` subclass)
and `Settings` inherits it. This recipe knows none of them; you add them here:

    from agentic.llm.settings import LLMSettings        # block from the langchain-agent recipe

    class Settings(LLMSettings, BaseAppSettings): ...

- Field names are case-insensitive env vars: `app_name` <- `APP_NAME`.
- Real env vars win over `.env` (production injects them; `.env` is for local dev).
- Secrets are `SecretStr`: they never show up in logs or `repr`.
- Tests: `Settings(_env_file=None, ...)`, or `get_settings.cache_clear()` after changing env vars.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    """Fields every backend has. Blocks from other recipes are mixed in by `Settings`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "{{app_name}}"
    environment: str = "local"  # local | staging | production
    debug: bool = False
    log_level: str = "INFO"


class Settings(BaseAppSettings):
    """The project's settings. Add blocks as parents: `class Settings(LLMSettings, BaseAppSettings)`."""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
