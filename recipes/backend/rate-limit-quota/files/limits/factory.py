"""The one place that builds the limits from the backend the settings name. There is no default."""

from collections.abc import Callable
from typing import Any

from .base import Clock, QuotaStore, RateLimiter, TurnLimits, utc_now
from .models import LimitsBackend
from .settings import LimitsSettings

SessionFactory = Callable[[], Any] | None


class LimitsFactory:
    @staticmethod
    def create(settings: LimitsSettings, *, session_factory: SessionFactory = None, clock: Clock = utc_now) -> TurnLimits:
        """Build `TurnLimits` for `settings.limits_backend`. Once at startup:

            app.state.turn_limits = LimitsFactory.create(get_settings(), session_factory=SessionLocal)

        `SQL` needs the app's `session_factory`. Unknown backend -> ValueError.
        """
        return TurnLimits(
            quota=LimitsFactory.create_quota_store(settings, session_factory=session_factory, clock=clock),
            rate_limiter=LimitsFactory.create_rate_limiter(settings, session_factory=session_factory, clock=clock),
            unit=settings.quota_unit,
        )

    @staticmethod
    def create_rate_limiter(
        settings: LimitsSettings, *, session_factory: SessionFactory = None, clock: Clock = utc_now
    ) -> RateLimiter | None:
        """None when RATE_LIMIT_ENABLED=false."""
        if not settings.rate_limit_enabled:
            return None
        kwargs: dict[str, Any] = dict(
            max_requests=settings.rate_limit_requests, window_seconds=settings.rate_limit_window_seconds, clock=clock
        )
        match settings.limits_backend:
            case LimitsBackend.IN_MEMORY:
                from .in_memory import InMemoryRateLimiter

                return InMemoryRateLimiter(**kwargs)
            case LimitsBackend.SQL:
                from .sql import SqlRateLimiter

                return SqlRateLimiter(_required(session_factory), **kwargs)
        raise ValueError(f"Unknown limits backend: {settings.limits_backend!r}")

    @staticmethod
    def create_quota_store(
        settings: LimitsSettings, *, session_factory: SessionFactory = None, clock: Clock = utc_now
    ) -> QuotaStore:
        kwargs: dict[str, Any] = dict(limits=settings.quota_limits, clock=clock)
        match settings.limits_backend:
            case LimitsBackend.IN_MEMORY:
                from .in_memory import InMemoryQuotaStore

                return InMemoryQuotaStore(**kwargs)
            case LimitsBackend.SQL:
                from .sql import SqlQuotaStore

                return SqlQuotaStore(_required(session_factory), **kwargs)
        raise ValueError(f"Unknown limits backend: {settings.limits_backend!r}")


def _required(session_factory: SessionFactory) -> Callable[[], Any]:
    if session_factory is None:
        raise ValueError("LIMITS_BACKEND=sql needs the app's session_factory")
    return session_factory
