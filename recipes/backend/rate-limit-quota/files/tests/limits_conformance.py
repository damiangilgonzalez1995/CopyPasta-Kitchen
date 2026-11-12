"""Behaviour every backend must have. A new backend = a subclass with a fixture.

    class TestRedisRateLimiter(RateLimiterConformance):
        @pytest.fixture
        def limiter(self, clock): return RedisRateLimiter(redis, max_requests=3, window_seconds=60, clock=clock)

    class TestRedisQuotaStore(QuotaStoreConformance):
        @pytest.fixture
        def quota(self, clock): return RedisQuotaStore(redis, limits=QuotaLimits(daily=2, monthly=3), clock=clock)

The `clock` fixture is a `FakeClock`: tests move time with `clock.advance(seconds)` / `clock.set(dt)`.
"""

from datetime import UTC, datetime, timedelta

import pytest

from limits import QuotaExhausted, QuotaPeriod, RateLimited

MAX_REQUESTS = 3
WINDOW = 60
DAILY, MONTHLY = 2, 3
START = datetime(2026, 3, 30, 10, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    def set(self, now: datetime) -> None:
        self.now = now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


class RateLimiterConformance:
    """Fixture `limiter`: `max_requests=MAX_REQUESTS`, `window_seconds=WINDOW`, `clock=clock`."""

    async def test_allows_up_to_the_limit_and_counts_down(self, limiter):
        remaining = [(await limiter.check("u1")).remaining for _ in range(MAX_REQUESTS)]
        assert remaining == [2, 1, 0]

    async def test_refuses_the_next_one_with_retry_after(self, limiter, clock):
        for _ in range(MAX_REQUESTS):
            await limiter.check("u1")
        clock.advance(10)

        with pytest.raises(RateLimited) as exc:
            await limiter.check("u1")

        assert exc.value.code == "rate_limited"
        assert exc.value.retry_after == WINDOW - 10
        assert exc.value.resets_at == START + timedelta(seconds=WINDOW)

    async def test_refused_requests_are_not_counted(self, limiter, clock):
        for _ in range(MAX_REQUESTS):
            await limiter.check("u1")
        for _ in range(5):
            with pytest.raises(RateLimited):
                await limiter.check("u1")
        clock.advance(WINDOW)

        assert (await limiter.check("u1")).remaining == MAX_REQUESTS - 1

    async def test_window_slides_one_slot_at_a_time(self, limiter, clock):
        await limiter.check("u1")
        clock.advance(30)
        await limiter.check("u1")
        await limiter.check("u1")
        clock.advance(31)  # only the first hit has left the window

        assert (await limiter.check("u1")).remaining == 0
        with pytest.raises(RateLimited) as exc:
            await limiter.check("u1")
        assert exc.value.retry_after == 29

    async def test_subjects_are_independent(self, limiter):
        for _ in range(MAX_REQUESTS):
            await limiter.check("u1")

        assert (await limiter.check("u2")).remaining == MAX_REQUESTS - 1


class QuotaStoreConformance:
    """Fixture `quota`: `limits=QuotaLimits(daily=DAILY, monthly=MONTHLY)`, `clock=clock`."""

    async def test_unknown_tenant_has_everything_available(self, quota):
        status = await quota.status("t1")
        assert status.available and status.exhausted is None and status.resets_at is None
        assert (status.daily.used, status.daily.limit) == (0, DAILY)
        assert (status.monthly.used, status.monthly.limit) == (0, MONTHLY)

    async def test_record_accumulates_and_daily_exhausts_first(self, quota):
        await quota.record("t1", 1)
        await quota.record("t1", 0.5)
        assert (await quota.status("t1")).daily.used == 1.5

        await quota.record("t1", 0.5)
        with pytest.raises(QuotaExhausted) as exc:
            await quota.ensure_available("t1")

        assert exc.value.code == "ai_quota_daily_exhausted"
        assert exc.value.period == QuotaPeriod.DAILY
        assert exc.value.resets_at == datetime(2026, 3, 31, tzinfo=UTC)

    async def test_daily_resets_at_midnight_utc_but_monthly_keeps_counting(self, quota, clock):
        await quota.record("t1", DAILY)
        clock.set(datetime(2026, 3, 31, 0, 0, 1, tzinfo=UTC))

        status = await quota.ensure_available("t1")

        assert status.daily.used == 0 and status.monthly.used == DAILY

    async def test_monthly_exhausts_and_resets_on_the_first_of_next_month(self, quota, clock):
        await quota.record("t1", DAILY)
        clock.set(datetime(2026, 3, 31, 12, 0, tzinfo=UTC))
        await quota.record("t1", MONTHLY - DAILY)

        with pytest.raises(QuotaExhausted) as exc:
            await quota.ensure_available("t1")
        assert exc.value.code == "ai_quota_monthly_exhausted"
        assert exc.value.resets_at == datetime(2026, 4, 1, tzinfo=UTC)

        clock.set(datetime(2026, 4, 1, tzinfo=UTC))
        assert (await quota.status("t1")).monthly.used == 0

    async def test_tenants_are_independent(self, quota):
        await quota.record("t1", DAILY)

        assert (await quota.status("t2")).available
        assert not (await quota.status("t1")).available

    async def test_recording_zero_or_negative(self, quota):
        await quota.record("t1", 0)
        assert (await quota.status("t1")).daily.used == 0
        with pytest.raises(ValueError):
            await quota.record("t1", -1)
