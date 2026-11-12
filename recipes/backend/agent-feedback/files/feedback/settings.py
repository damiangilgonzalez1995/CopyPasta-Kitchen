"""Feedback settings BLOCK, meant to be mixed into the project settings (`project-settings` recipe):

    class Settings(FeedbackSettings, BaseAppSettings): ...

Env vars: FEEDBACK_BACKEND (required: in_memory | sql).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import FeedbackBackend


class FeedbackSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # No default on purpose: votes kept "just in case" in process memory vanish on every restart.
    feedback_backend: FeedbackBackend
