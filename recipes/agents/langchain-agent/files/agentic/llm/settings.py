"""Credentials the LLM factory needs. Injected from the app; `agentic/` never reads a settings singleton."""

import os

from pydantic import BaseModel, SecretStr

from .models import LLMProviderName


class LLMSettings(BaseModel):
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    azure_openai_api_key: SecretStr | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str | None = None

    timeout_seconds: float = 60.0
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> "LLMSettings":
        """Convenience for scripts and tests. In the app, build it from your own settings object."""
        env = os.environ.get
        return cls(
            openai_api_key=env("OPENAI_API_KEY"),
            anthropic_api_key=env("ANTHROPIC_API_KEY"),
            groq_api_key=env("GROQ_API_KEY"),
            azure_openai_api_key=env("AZURE_OPENAI_API_KEY"),
            azure_openai_endpoint=env("AZURE_OPENAI_ENDPOINT"),
            azure_openai_api_version=env("AZURE_OPENAI_API_VERSION"),
        )

    def api_key_for(self, provider: LLMProviderName) -> SecretStr:
        key = {
            LLMProviderName.OPENAI: self.openai_api_key,
            LLMProviderName.ANTHROPIC: self.anthropic_api_key,
            LLMProviderName.GROQ: self.groq_api_key,
            LLMProviderName.AZURE_OPENAI: self.azure_openai_api_key,
        }[provider]
        if key is None:
            raise ValueError(f"Missing API key for provider {provider.value!r}")
        return key
