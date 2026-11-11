"""LLM settings BLOCK: the config this recipe needs, meant to be mixed into the project settings.

This recipe does not ship the project settings (that is the `project-settings` recipe, or the
one your backend already has). It only brings this block:

    # core/config.py
    from agentic.llm.settings import LLMSettings

    class Settings(LLMSettings, BaseAppSettings): ...

Env vars it reads: OPENAI_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY, AZURE_OPENAI_API_KEY,
AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION, LLM_TIMEOUT_SECONDS, LLM_MAX_RETRIES,
ASSISTANT_MODEL, CLASSIFIER_MODEL.
"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# The ONLY line that knows where the project settings live. Change it to your path.
PROJECT_SETTINGS = "core.config"


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    azure_openai_api_key: SecretStr | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str | None = None

    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2

    # Model per agent, as an LLMModel id (see models.py)
    assistant_model: str = "gpt-4.1-mini"
    classifier_model: str = "gpt-4.1-nano"

    def api_key_for(self, provider: str) -> SecretStr:
        """`provider` is an `LLMProviderName` value: openai | anthropic | groq | azure_openai."""
        key: SecretStr | None = getattr(self, f"{provider}_api_key", None)
        if key is None or not key.get_secret_value():
            raise ValueError(f"Missing API key for provider {provider!r}: set {provider.upper()}_API_KEY")
        return key


def get_llm_settings() -> LLMSettings:
    """The project settings (which inherit `LLMSettings`). Imported lazily: copying this recipe
    alone never breaks on import; it only fails here, with a clear message, if nothing is wired."""
    from importlib import import_module

    try:
        settings = import_module(PROJECT_SETTINGS).get_settings()
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            f"No project settings at {PROJECT_SETTINGS!r}.get_settings(). Add the `project-settings` "
            "recipe (or point PROJECT_SETTINGS at yours) and mix LLMSettings into its Settings."
        ) from exc
    if not isinstance(settings, LLMSettings):
        raise RuntimeError("The project Settings must inherit LLMSettings: class Settings(LLMSettings, ...)")
    return settings
