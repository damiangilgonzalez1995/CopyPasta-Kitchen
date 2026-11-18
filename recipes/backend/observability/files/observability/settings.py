"""Observability settings BLOCK, meant to be mixed into the project settings (`project-settings`):

    class Settings(ObservabilitySettings, LLMSettings, BaseAppSettings): ...

Env vars (nothing traces unless TRACING_PROVIDER names a provider):
    TRACING_PROVIDER=none|langfuse|opik|langsmith     default none
    TRACING_TAGS=prod,eu                              tags on every trace (comma-separated)
    TRACING_FLUSH_TIMEOUT_SECONDS=2
    LANGFUSE_PUBLIC_KEY  LANGFUSE_SECRET_KEY  LANGFUSE_HOST=https://cloud.langfuse.com
    OPIK_URL_OVERRIDE (self-hosted, e.g. http://localhost:5173/api)  OPIK_API_KEY + OPIK_WORKSPACE (Cloud)  OPIK_PROJECT_NAME
    LANGSMITH_API_KEY  LANGSMITH_ENDPOINT=https://api.smith.langchain.com  LANGSMITH_PROJECT
"""

from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from .models import TracingProvider


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    tracing_provider: TracingProvider = TracingProvider.NONE
    tracing_tags: Annotated[list[str], NoDecode] = Field(default_factory=list)
    tracing_flush_timeout_seconds: float = Field(default=2.0, gt=0)

    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    opik_url_override: str | None = None
    opik_api_key: SecretStr | None = None
    opik_workspace: str | None = None
    opik_project_name: str = "{{app_name}}"

    langsmith_api_key: SecretStr | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "{{app_name}}"

    @field_validator("tracing_tags", mode="before")
    @classmethod
    def _split_commas(cls, value):
        if isinstance(value, str):
            return [tag.strip() for tag in value.split(",") if tag.strip()]
        return value

    @model_validator(mode="after")
    def _provider_has_its_keys(self) -> "ObservabilitySettings":
        match self.tracing_provider:
            case TracingProvider.LANGFUSE if not (self.langfuse_public_key and self.langfuse_secret_key):
                raise ValueError("TRACING_PROVIDER=langfuse needs LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY")
            case TracingProvider.OPIK if not (self.opik_url_override or self.opik_api_key):
                raise ValueError("TRACING_PROVIDER=opik needs OPIK_URL_OVERRIDE (self-hosted) or OPIK_API_KEY (Cloud)")
            case TracingProvider.LANGSMITH if not self.langsmith_api_key:
                raise ValueError("TRACING_PROVIDER=langsmith needs LANGSMITH_API_KEY")
        return self
