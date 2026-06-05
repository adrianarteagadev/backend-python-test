from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from notification_service.application.types import ProcessRequestOutcome
from notification_service.domain.exceptions import (
    NonRetryableProviderError,
    RequestNotFoundError,
    RetryableProviderError,
)
from notification_service.domain.models import RequestStatus
from notification_service.infrastructure.provider_client import ProviderClient
from notification_service.infrastructure.rate_limiter import SlidingWindowRateLimiter
from notification_service.infrastructure.repositories import (
    InMemoryNotificationRequestRepository,
)
from notification_service.infrastructure.settings import Settings


class NotificationProcessingCoordinator:
    def __init__(
        self,
        repository: InMemoryNotificationRequestRepository,
        provider_client: ProviderClient,
        rate_limiter: SlidingWindowRateLimiter,
        settings: Settings,
        *,
        sleep_func: Callable[[float], Awaitable[None]] | None = None,
        jitter_func: Callable[[], float] | None = None,
    ) -> None:
        self._repository = repository
        self._provider_client = provider_client
        self._rate_limiter = rate_limiter
        self._settings = settings
        self._sleep = sleep_func or asyncio.sleep
        self._jitter = jitter_func or random.random
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._scheduled: set[str] = set()
        self._coordination_lock = asyncio.Lock()
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._logger = logging.getLogger(self.__class__.__name__)

    async def start(self) -> None:
        if self._worker_tasks:
            return

        self._worker_tasks = [
            asyncio.create_task(self._worker_loop(worker_id), name=f"notification-worker-{worker_id}")
            for worker_id in range(self._settings.worker_count)
        ]

    async def stop(self) -> None:
        for task in self._worker_tasks:
            task.cancel()

        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            self._worker_tasks.clear()

        await self._provider_client.close()

    async def submit(self, request_id: str) -> ProcessRequestOutcome:
        async with self._coordination_lock:
            notification_request = await self._repository.get(request_id)
            if notification_request is None:
                raise RequestNotFoundError(
                    f"Notification request '{request_id}' was not found."
                )

            if notification_request.status == RequestStatus.SENT:
                return ProcessRequestOutcome.ALREADY_SENT

            if (
                notification_request.status == RequestStatus.PROCESSING
                or request_id in self._scheduled
            ):
                return ProcessRequestOutcome.ALREADY_PROCESSING

            if notification_request.status == RequestStatus.FAILED:
                await self._repository.mark_queued(request_id)

            self._scheduled.add(request_id)
            await self._queue.put(request_id)
            self._logger.info("notification_enqueued request_id=%s", request_id)
            return ProcessRequestOutcome.ENQUEUED

    async def _worker_loop(self, worker_id: int) -> None:
        while True:
            request_id = await self._queue.get()
            try:
                await self._claim_and_process(request_id, worker_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.exception(
                    "notification_processing_unhandled_error worker_id=%s request_id=%s",
                    worker_id,
                    request_id,
                )
            finally:
                self._queue.task_done()

    async def _claim_and_process(self, request_id: str, worker_id: int) -> None:
        async with self._coordination_lock:
            self._scheduled.discard(request_id)
            notification_request = await self._repository.get(request_id)
            if notification_request is None:
                return
            if notification_request.status == RequestStatus.SENT:
                return
            await self._repository.mark_processing(request_id)

        await self._deliver(request_id, worker_id)

    async def _deliver(self, request_id: str, worker_id: int) -> None:
        notification_request = await self._repository.require(request_id)
        last_error = "Provider retries exhausted."

        for attempt in range(1, self._settings.max_retry_attempts + 1):
            try:
                await self._rate_limiter.acquire()
                provider_id = await self._provider_client.send_notification(notification_request)
                await self._repository.mark_sent(request_id, provider_id)
                self._logger.info(
                    "notification_sent worker_id=%s request_id=%s attempt=%s provider_id=%s",
                    worker_id,
                    request_id,
                    attempt,
                    provider_id,
                )
                return
            except RetryableProviderError as exc:
                last_error = str(exc)
                self._logger.warning(
                    "notification_retry worker_id=%s request_id=%s attempt=%s error=%s",
                    worker_id,
                    request_id,
                    attempt,
                    last_error,
                )
                if attempt == self._settings.max_retry_attempts:
                    break
                await self._sleep(self._compute_backoff(attempt))
            except NonRetryableProviderError as exc:
                error_message = str(exc)
                await self._repository.mark_failed(request_id, error_message)
                self._logger.error(
                    "notification_failed_non_retryable worker_id=%s request_id=%s error=%s",
                    worker_id,
                    request_id,
                    error_message,
                )
                return

        await self._repository.mark_failed(request_id, last_error)
        self._logger.error(
            "notification_failed_retries_exhausted worker_id=%s request_id=%s error=%s",
            worker_id,
            request_id,
            last_error,
        )

    def _compute_backoff(self, attempt: int) -> float:
        base_delay = self._settings.base_backoff_seconds * (2 ** (attempt - 1))
        bounded_delay = min(base_delay, self._settings.max_backoff_seconds)
        return bounded_delay + (bounded_delay * 0.1 * self._jitter())
