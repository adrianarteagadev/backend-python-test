from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_calls: int,
        period_seconds: float,
        *,
        clock: Callable[[], float] | None = None,
        sleep_func: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._max_calls = max_calls
        self._period_seconds = period_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._clock = clock or time.monotonic
        self._sleep = sleep_func or asyncio.sleep

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                current_time = self._clock()
                self._evict_expired(current_time)

                if len(self._timestamps) < self._max_calls:
                    self._timestamps.append(current_time)
                    return

                wait_time = self._period_seconds - (current_time - self._timestamps[0])

            await self._sleep(max(wait_time, 0.001))

    def _evict_expired(self, current_time: float) -> None:
        while self._timestamps and current_time - self._timestamps[0] >= self._period_seconds:
            self._timestamps.popleft()
