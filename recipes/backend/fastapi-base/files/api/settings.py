"""API settings BLOCK, meant to be mixed into the project settings (`project-settings` recipe):

    class Settings(ApiSettings, BaseAppSettings): ...

Env vars: CORS_ORIGINS (comma-separated, empty = no CORS middleware), DOCS_ENABLED (false).
"""

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # NoDecode: pydantic-settings would otherwise expect JSON in the env var; we want "a, b".
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Origins allowed to call the API from a browser. Empty: no CORS headers at all.",
    )
    docs_enabled: bool = Field(
        default=False,
        description="/docs and /openapi.json publish the whole map of the API: development only.",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_commas(cls, value):
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value
