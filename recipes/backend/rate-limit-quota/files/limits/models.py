from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LimitsBackend(StrEnum):
    """Where hits and usage are stored. Chosen in the settings (`LIMITS_BACKEND`), built by `LimitsFactory`.

    IN_MEMORY: dicts of the process. Not shared between workers: tests and single-process dev.
    SQL: tables `rate_limit_hits` and `ai_usage_daily` (Postgres/Supabase; SQLite in tests).
    """

    IN_MEMORY = "in_memory"
    SQL = "sql"


class QuotaUnit(StrEnum):
    """What the quota counts. REQUESTS: one per turn, recorded by `TurnLimits.allow`.
    COST: money or tokens, recorded by YOUR code with `QuotaStore.record` once the turn is priced."""

    REQUESTS = "requests"
    COST = "cost"


class QuotaPeriod(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"


# --- Rate limit ------------------------------------------------------------------------------


class WindowState(BaseModel):
    """What a backend reports from `_acquire`: hits already inside the window (this one excluded)
    and the oldest of them, which decides when the next slot frees up."""

    model_config = ConfigDict(frozen=True)

    count: int = Field(ge=0)
    oldest: float | None = Field(default=None, description="Epoch seconds of the oldest hit in the window.")


class RateLimitDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    remaining: int = Field(ge=0, description="Requests left in the window after this one.")
    resets_at: datetime = Field(description="When the window is empty again if nothing else arrives.")


class RateLimited(Exception):
    """Too many requests in the window. `retry_after` is whole seconds, never 0."""

    code = "rate_limited"

    def __init__(self, *, retry_after: int, resets_at: datetime) -> None:
        super().__init__(f"rate limited, retry in {retry_after}s")
        self.retry_after = retry_after
        self.resets_at = resets_at


# --- Quota -----------------------------------------------------------------------------------


class QuotaLimits(BaseModel):
    """Limits for one tenant. `None` = unlimited for that period."""

    model_config = ConfigDict(frozen=True)

    daily: float | None = Field(default=None, ge=0)
    monthly: float | None = Field(default=None, ge=0)


class PeriodUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    used: float = Field(ge=0)
    limit: float | None = None
    resets_at: datetime

    @property
    def exhausted(self) -> bool:
        return self.limit is not None and self.used >= self.limit


class QuotaStatus(BaseModel):
    """What `GET /agent/quota` returns and what the frontend needs: can I ask, and if not, until when."""

    model_config = ConfigDict(frozen=True)

    available: bool
    exhausted: QuotaPeriod | None = None
    resets_at: datetime | None = Field(default=None, description="Only when exhausted.")
    daily: PeriodUsage
    monthly: PeriodUsage


class QuotaExhausted(Exception):
    """The tenant spent its daily or monthly quota. `code` is what the API sends and the frontend reads."""

    def __init__(self, *, period: QuotaPeriod, resets_at: datetime) -> None:
        super().__init__(f"{period} quota exhausted until {resets_at.isoformat()}")
        self.period = period
        self.resets_at = resets_at

    @property
    def code(self) -> str:
        return f"ai_quota_{self.period}_exhausted"
