"""Process-local backends: tests and single-process development. Lost on restart, not shared
between workers (each worker would have its own window and its own counters)."""

from collections import defaultdict
from datetime import date

from .base import QuotaStore, RateLimiter
from .models import WindowState


class InMemoryRateLimiter(RateLimiter):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def _acquire(self, subject: str, *, now: float, window_start: float, limit: int) -> WindowState:
        hits = [t for t in self._hits[subject] if t > window_start]
        state = WindowState(count=len(hits), oldest=min(hits) if hits else None)
        if state.count < limit:
            hits.append(now)
        self._hits[subject] = hits
        return state


class InMemoryQuotaStore(QuotaStore):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._usage_by_day: dict[tuple[str, date], float] = defaultdict(float)

    async def _usage(self, tenant_id: str, *, day: date, month_start: date) -> tuple[float, float]:
        daily = self._usage_by_day.get((tenant_id, day), 0.0)
        monthly = sum(v for (t, d), v in self._usage_by_day.items() if t == tenant_id and month_start <= d <= day)
        return daily, monthly

    async def _add_usage(self, tenant_id: str, *, day: date, amount: float) -> None:
        self._usage_by_day[(tenant_id, day)] += amount
