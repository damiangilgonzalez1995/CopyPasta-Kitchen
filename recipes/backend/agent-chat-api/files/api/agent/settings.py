"""Settings block of the chat endpoints. The project `Settings` inherits it (project-settings)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_endpoint_enabled: bool = Field(
        default=True,
        description="Kill switch. Off -> the chat routes answer 404, as if they did not exist.",
    )
    chat_max_question_length: int = Field(default=4000, ge=1, description="Longer questions get a 400.")
