"""Rate limit and usage quota for agent turns. Independent of FastAPI and of the agent.

The logic (sliding window, daily/monthly periods, resets, errors) lives in the base classes.
A backend only stores: `RateLimiter._acquire` and `QuotaStore._usage` / `_add_usage`.
Backend chosen in the settings (`LIMITS_BACKEND`), built by `LimitsFactory`.
"""

from .base import QuotaStore, RateLimiter, TurnLimits
from .factory import LimitsFactory
from .in_memory import InMemoryQuotaStore, InMemoryRateLimiter
from .models import (
    LimitsBackend,
    PeriodUsage,
    QuotaExhausted,
    QuotaLimits,
    QuotaPeriod,
    QuotaStatus,
    QuotaUnit,
    RateLimitDecision,
    RateLimited,
    WindowState,
)
from .settings import LimitsSettings

__all__ = [
    "InMemoryQuotaStore",
    "InMemoryRateLimiter",
    "LimitsBackend",
    "LimitsFactory",
    "LimitsSettings",
    "PeriodUsage",
    "QuotaExhausted",
    "QuotaLimits",
    "QuotaPeriod",
    "QuotaStatus",
    "QuotaStore",
    "QuotaUnit",
    "RateLimitDecision",
    "RateLimited",
    "RateLimiter",
    "TurnLimits",
    "WindowState",
]
