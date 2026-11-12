"""SQL backends with SQLAlchemy 2 (Postgres/Supabase in production, SQLite in tests).

Same pattern as `agent-memory`: the app's `session_factory`, sync queries in `asyncio.to_thread`.

- `rate_limit_hits`: one row per allowed request. `_acquire` deletes the old ones, counts, inserts,
  all in one transaction. Fine up to a few requests per second per user; beyond that, Redis
  (a sorted set + Lua, see RECIPE.md).
- `ai_usage_daily`: one row per tenant and day, `amount` accumulated. Monthly usage is the sum
  of the month's rows. Keep it: it is also your usage report.
"""

import asyncio
from collections.abc import Callable
from datetime import date

from sqlalchemy import Column, Date, Float, Integer, MetaData, String, Table, UniqueConstraint, delete, func, select
from sqlalchemy.orm import Session

from .base import QuotaStore, RateLimiter
from .models import WindowState

metadata = MetaData()

rate_limit_hits = Table(
    "rate_limit_hits",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("subject", String, nullable=False, index=True),
    Column("ts", Float, nullable=False),  # epoch seconds
)

ai_usage_daily = Table(
    "ai_usage_daily",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("day", Date, nullable=False),
    Column("amount", Float, nullable=False, default=0.0),
    UniqueConstraint("tenant_id", "day", name="uq_ai_usage_daily_tenant_day"),
)


class SqlRateLimiter(RateLimiter):
    def __init__(self, session_factory: Callable[[], Session], **kwargs) -> None:
        super().__init__(**kwargs)
        self._session_factory = session_factory

    async def _acquire(self, subject: str, *, now: float, window_start: float, limit: int) -> WindowState:
        return await asyncio.to_thread(self._acquire_sync, subject, now, window_start, limit)

    def _acquire_sync(self, subject: str, now: float, window_start: float, limit: int) -> WindowState:
        mine = rate_limit_hits.c.subject == subject
        with self._session_factory() as db:
            db.execute(delete(rate_limit_hits).where(mine, rate_limit_hits.c.ts <= window_start))
            count, oldest = db.execute(select(func.count(), func.min(rate_limit_hits.c.ts)).where(mine)).one()
            if count < limit:
                db.execute(rate_limit_hits.insert().values(subject=subject, ts=now))
            db.commit()
        return WindowState(count=count, oldest=oldest)


class SqlQuotaStore(QuotaStore):
    def __init__(self, session_factory: Callable[[], Session], **kwargs) -> None:
        super().__init__(**kwargs)
        self._session_factory = session_factory

    async def _usage(self, tenant_id: str, *, day: date, month_start: date) -> tuple[float, float]:
        return await asyncio.to_thread(self._usage_sync, tenant_id, day, month_start)

    def _usage_sync(self, tenant_id: str, day: date, month_start: date) -> tuple[float, float]:
        mine = ai_usage_daily.c.tenant_id == tenant_id
        with self._session_factory() as db:
            daily = db.execute(select(ai_usage_daily.c.amount).where(mine, ai_usage_daily.c.day == day)).scalar()
            monthly = db.execute(
                select(func.coalesce(func.sum(ai_usage_daily.c.amount), 0.0)).where(
                    mine, ai_usage_daily.c.day >= month_start, ai_usage_daily.c.day <= day
                )
            ).scalar()
        return float(daily or 0.0), float(monthly or 0.0)

    async def _add_usage(self, tenant_id: str, *, day: date, amount: float) -> None:
        await asyncio.to_thread(self._add_usage_sync, tenant_id, day, amount)

    def _add_usage_sync(self, tenant_id: str, day: date, amount: float) -> None:
        # Read-then-write in one transaction. On Postgres under heavy concurrency prefer
        # `insert(...).on_conflict_do_update(...)` from sqlalchemy.dialects.postgresql.
        where = (ai_usage_daily.c.tenant_id == tenant_id, ai_usage_daily.c.day == day)
        with self._session_factory() as db:
            current = db.execute(select(ai_usage_daily.c.amount).where(*where)).scalar()
            if current is None:
                db.execute(ai_usage_daily.insert().values(tenant_id=tenant_id, day=day, amount=amount))
            else:
                db.execute(ai_usage_daily.update().where(*where).values(amount=current + amount))
            db.commit()
