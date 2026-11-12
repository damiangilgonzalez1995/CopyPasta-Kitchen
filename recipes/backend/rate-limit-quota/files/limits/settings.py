"""Limits settings BLOCK, meant to be mixed into the project settings (`project-settings` recipe):

    class Settings(LimitsSettings, BaseAppSettings): ...

Env vars: LIMITS_BACKEND (required: in_memory | sql), RATE_LIMIT_ENABLED (true), RATE_LIMIT_REQUESTS (20),
RATE_LIMIT_WINDOW_SECONDS (60), QUOTA_UNIT (requests | cost), QUOTA_DAILY_LIMIT and QUOTA_MONTHLY_LIMIT
(empty = unlimited).
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import LimitsBackend, QuotaLimits, QuotaUnit


class LimitsSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # No default on purpose: in-process limits "just in case" are a limit per worker, not per user.
    limits_backend: LimitsBackend

    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=20, ge=1, description="Per user and window.")
    rate_limit_window_seconds: int = Field(default=60, ge=1)

    quota_unit: QuotaUnit = QuotaUnit.REQUESTS
    quota_daily_limit: float | None = Field(default=None, ge=0, description="Per tenant. Empty = unlimited.")
    quota_monthly_limit: float | None = Field(default=None, ge=0, description="Per tenant. Empty = unlimited.")

    @property
    def quota_limits(self) -> QuotaLimits:
        return QuotaLimits(daily=self.quota_daily_limit, monthly=self.quota_monthly_limit)
