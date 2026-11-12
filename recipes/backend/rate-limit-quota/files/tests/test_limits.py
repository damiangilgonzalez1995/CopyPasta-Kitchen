from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from limits import (
    InMemoryQuotaStore,
    InMemoryRateLimiter,
    LimitsBackend,
    LimitsFactory,
    LimitsSettings,
    QuotaExhausted,
    QuotaLimits,
    QuotaUnit,
    RateLimited,
    TurnLimits,
)
from limits.sql import SqlQuotaStore, SqlRateLimiter, metadata

from .limits_conformance import (  # noqa: F401  (clock: fixture used by the conformance classes)
    DAILY,
    MAX_REQUESTS,
    MONTHLY,
    WINDOW,
    FakeClock,
    QuotaStoreConformance,
    RateLimiterConformance,
    clock,
)


def sqlite_session_factory():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    return sessionmaker(engine)


LIMITS = QuotaLimits(daily=DAILY, monthly=MONTHLY)


class TestInMemoryRateLimiter(RateLimiterConformance):
    @pytest.fixture
    def limiter(self, clock):
        return InMemoryRateLimiter(max_requests=MAX_REQUESTS, window_seconds=WINDOW, clock=clock)


class TestSqlRateLimiter(RateLimiterConformance):
    @pytest.fixture
    def limiter(self, clock):
        return SqlRateLimiter(sqlite_session_factory(), max_requests=MAX_REQUESTS, window_seconds=WINDOW, clock=clock)


class TestInMemoryQuotaStore(QuotaStoreConformance):
    @pytest.fixture
    def quota(self, clock):
        return InMemoryQuotaStore(limits=LIMITS, clock=clock)


class TestSqlQuotaStore(QuotaStoreConformance):
    @pytest.fixture
    def quota(self, clock):
        return SqlQuotaStore(sqlite_session_factory(), limits=LIMITS, clock=clock)


# --- TurnLimits: the facade a turn calls -----------------------------------------------------


def turn_limits(unit: QuotaUnit = QuotaUnit.REQUESTS, *, rate_limiter: bool = True) -> TurnLimits:
    clock = FakeClock()
    return TurnLimits(
        quota=InMemoryQuotaStore(limits=QuotaLimits(daily=2), clock=clock),
        rate_limiter=InMemoryRateLimiter(max_requests=1, window_seconds=60, clock=clock) if rate_limiter else None,
        unit=unit,
    )


async def test_requests_unit_counts_each_allowed_turn():
    limits = turn_limits(rate_limiter=False)
    await limits.allow("t1", "u1")
    await limits.allow("t1", "u2")

    with pytest.raises(QuotaExhausted):
        await limits.allow("t1", "u3")
    assert (await limits.status("t1")).daily.used == 2


async def test_cost_unit_records_nothing_until_you_do():
    limits = turn_limits(QuotaUnit.COST, rate_limiter=False)
    for _ in range(5):
        await limits.allow("t1", "u1")
    assert (await limits.status("t1")).daily.used == 0

    await limits.quota.record("t1", 2.0)  # your code, once the turn is priced
    with pytest.raises(QuotaExhausted):
        await limits.allow("t1", "u1")


async def test_quota_is_checked_before_the_rate_limit_and_a_refused_turn_is_not_counted():
    limits = turn_limits()
    await limits.allow("t1", "u1")

    with pytest.raises(RateLimited):
        await limits.allow("t1", "u1")
    assert (await limits.status("t1")).daily.used == 1

    await limits.quota.record("t1", 1)  # tenant exhausted: quota wins even for a fresh user
    with pytest.raises(QuotaExhausted):
        await limits.allow("t1", "u2")


async def test_per_tenant_limits_by_overriding_limits():
    class TenantTableQuota(InMemoryQuotaStore):
        async def _limits(self, tenant_id):
            return QuotaLimits(daily=10) if tenant_id == "premium" else self.default_limits

    quota = TenantTableQuota(limits=QuotaLimits(daily=1), clock=FakeClock())
    await quota.record("premium", 1)
    await quota.record("basic", 1)

    assert (await quota.status("premium")).available
    assert not (await quota.status("basic")).available


# --- Settings + factory: the backend is chosen in .env, not in code ---------------------------


def test_everything_comes_from_env(monkeypatch):
    monkeypatch.setenv("LIMITS_BACKEND", "in_memory")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "5")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "30")
    monkeypatch.setenv("QUOTA_UNIT", "cost")
    monkeypatch.setenv("QUOTA_DAILY_LIMIT", "2.5")

    limits = LimitsFactory.create(LimitsSettings())

    assert isinstance(limits.quota, InMemoryQuotaStore) and isinstance(limits.rate_limiter, InMemoryRateLimiter)
    assert (limits.rate_limiter.max_requests, limits.rate_limiter.window_seconds) == (5, 30)
    assert limits.unit == QuotaUnit.COST
    assert limits.quota.default_limits == QuotaLimits(daily=2.5, monthly=None)


def test_switching_to_sql_is_only_a_setting():
    limits = LimitsFactory.create(LimitsSettings(limits_backend="sql"), session_factory=sqlite_session_factory())
    assert isinstance(limits.quota, SqlQuotaStore) and isinstance(limits.rate_limiter, SqlRateLimiter)


def test_rate_limit_can_be_switched_off():
    limits = LimitsFactory.create(LimitsSettings(limits_backend="in_memory", rate_limit_enabled=False))
    assert limits.rate_limiter is None


def test_backend_is_required_and_validated(monkeypatch):
    monkeypatch.delenv("LIMITS_BACKEND", raising=False)
    with pytest.raises(ValidationError):
        LimitsSettings()
    with pytest.raises(ValidationError):
        LimitsSettings(limits_backend="redis")
    with pytest.raises(ValueError, match="session_factory"):
        LimitsFactory.create(LimitsSettings(limits_backend=LimitsBackend.SQL))


def test_default_clock_is_utc():
    store = InMemoryQuotaStore(limits=QuotaLimits())
    assert store._clock().tzinfo is UTC and abs((store._clock() - datetime.now(UTC)).total_seconds()) < 5
