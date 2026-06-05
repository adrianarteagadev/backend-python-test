import pytest

from notification_service.infrastructure.rate_limiter import SlidingWindowRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_waits_for_window_capacity() -> None:
    current_time = 0.0
    sleeps: list[float] = []

    def clock() -> float:
        return current_time

    async def fake_sleep(delay: float) -> None:
        nonlocal current_time
        sleeps.append(delay)
        current_time += delay

    limiter = SlidingWindowRateLimiter(
        max_calls=2,
        period_seconds=10.0,
        clock=clock,
        sleep_func=fake_sleep,
    )

    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()

    assert sleeps == [10.0]
