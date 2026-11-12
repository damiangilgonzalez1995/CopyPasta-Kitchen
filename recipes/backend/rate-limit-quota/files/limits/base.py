"""The contracts. All the deciding is here; a backend only stores and counts.

    RateLimiter   sliding window per subject (user, ip, api key...). Subclass: `_acquire`.
    QuotaStore    daily + monthly usage per tenant. Subclass: `_usage`, `_add_usage` (and
                  `_limits` when each tenant has its own limits in a table).
    TurnLimits    the facade a turn calls: quota first, then rate limit, then record.

Every backend passes `tests/limits_conformance.py`. Time comes from `clock` so tests move it.
Async even in memory: the contract follows the slowest backend (Redis, SQL).
"""

import math
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

from .models import (
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

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class RateLimiter(ABC):
    """At most `max_requests` per `window_seconds` and subject, sliding window.

    `check` raises `RateLimited` with `retry_after` (seconds until the oldest hit leaves the window),
    or returns a `RateLimitDecision`. A refused request is NOT recorded: retrying does not push the
    window further away.
    """

    def __init__(self, *, max_requests: int, window_seconds: int, clock: Clock = utc_now) -> None:
        if max_requests < 1 or window_seconds < 1:
            raise ValueError("max_requests and window_seconds must be >= 1")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock

    async def check(self, subject: str) -> RateLimitDecision:
        now = self._clock().timestamp()
        state = await self._acquire(subject, now=now, window_start=now - self.window_seconds, limit=self.max_requests)
        oldest = state.oldest if state.oldest is not None else now
        frees_at = oldest + self.window_seconds
        if state.count < self.max_requests:
            return RateLimitDecision(
                remaining=self.max_requests - state.count - 1,
                resets_at=datetime.fromtimestamp(frees_at, UTC),
            )
        raise RateLimited(retry_after=max(1, math.ceil(frees_at - now)), resets_at=datetime.fromtimestamp(frees_at, UTC))

    @abstractmethod
    async def _acquire(self, subject: str, *, now: float, window_start: float, limit: int) -> WindowState:
        """Drop hits at or before `window_start`, count the rest, and if `count < limit` record `now`.
        Return the count BEFORE recording and the oldest hit. Atomic where the backend allows it
        (Redis: one Lua script; SQL: one transaction)."""


class QuotaStore(ABC):
    """Usage per tenant and period. `ensure_available` is the guard; `record` is the meter.

    Periods are UTC calendar days and months. A limit of `None` is "unlimited". Limits come from
    the constructor; override `_limits` to read them per tenant (a `tenant_quota` table).
    """

    def __init__(self, *, limits: QuotaLimits, clock: Clock = utc_now) -> None:
        self.default_limits = limits
        self._clock = clock

    async def status(self, tenant_id: str) -> QuotaStatus:
        now = self._clock()
        today, month_start = now.date(), now.date().replace(day=1)
        limits = await self._limits(tenant_id)
        daily_used, monthly_used = await self._usage(tenant_id, day=today, month_start=month_start)
        daily = PeriodUsage(used=daily_used, limit=limits.daily, resets_at=next_day(today))
        monthly = PeriodUsage(used=monthly_used, limit=limits.monthly, resets_at=next_month(month_start))
        # Monthly first: it is the longer block, so the frontend shows the later reset.
        if monthly.exhausted:
            return QuotaStatus(
                available=False, exhausted=QuotaPeriod.MONTHLY, resets_at=monthly.resets_at, daily=daily, monthly=monthly
            )
        if daily.exhausted:
            return QuotaStatus(
                available=False, exhausted=QuotaPeriod.DAILY, resets_at=daily.resets_at, daily=daily, monthly=monthly
            )
        return QuotaStatus(available=True, daily=daily, monthly=monthly)

    async def ensure_available(self, tenant_id: str) -> QuotaStatus:
        """Raise `QuotaExhausted` (with the period and `resets_at`) or return the status."""
        status = await self.status(tenant_id)
        if not status.available:
            assert status.exhausted is not None and status.resets_at is not None
            raise QuotaExhausted(period=status.exhausted, resets_at=status.resets_at)
        return status

    async def record(self, tenant_id: str, amount: float = 1.0) -> None:
        """Add `amount` (requests, euros, tokens: whatever `QuotaUnit` says) to today's usage."""
        if amount < 0:
            raise ValueError("amount must be >= 0")
        if amount:
            await self._add_usage(tenant_id, day=self._clock().date(), amount=amount)

    async def _limits(self, tenant_id: str) -> QuotaLimits:
        """Limits for this tenant. Default: the ones from the settings, same for everyone."""
        return self.default_limits

    @abstractmethod
    async def _usage(self, tenant_id: str, *, day: date, month_start: date) -> tuple[float, float]:
        """(used on `day`, used from `month_start` to `day` inclusive). (0, 0) for an unknown tenant."""

    @abstractmethod
    async def _add_usage(self, tenant_id: str, *, day: date, amount: float) -> None:
        """Add `amount` to the tenant's counter for `day`, creating it if needed."""


class TurnLimits:
    """What a turn asks before it starts: `allow(tenant_id, user_id)`.

    Order: quota (the tenant is out of budget: nothing else matters), then rate limit (per user),
    then, with `QuotaUnit.REQUESTS`, the request is recorded. With `COST`, nothing is recorded here:
    call `quota.record(tenant_id, cost)` yourself when the turn is priced.
    `rate_limiter=None` disables the rate limit (RATE_LIMIT_ENABLED=false).
    """

    def __init__(self, *, quota: QuotaStore, rate_limiter: RateLimiter | None, unit: QuotaUnit) -> None:
        self.quota = quota
        self.rate_limiter = rate_limiter
        self.unit = unit

    async def allow(self, tenant_id: str, user_id: str) -> QuotaStatus:
        """Raise `QuotaExhausted` or `RateLimited`; otherwise return the quota status."""
        status = await self.quota.ensure_available(tenant_id)
        if self.rate_limiter is not None:
            await self.rate_limiter.check(f"{tenant_id}:{user_id}")
        if self.unit == QuotaUnit.REQUESTS:
            await self.quota.record(tenant_id, 1)
        return status

    async def status(self, tenant_id: str) -> QuotaStatus:
        return await self.quota.status(tenant_id)


def next_day(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, UTC)


def next_month(month_start: date) -> datetime:
    first = month_start.replace(day=1)
    following = first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(month=first.month + 1)
    return datetime.combine(following, time.min, UTC)
