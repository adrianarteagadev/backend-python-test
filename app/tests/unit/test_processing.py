import asyncio
from collections import deque
from dataclasses import replace

import pytest

from notification_service.application.processing import NotificationProcessingCoordinator
from notification_service.application.types import ProcessRequestOutcome
from notification_service.domain.exceptions import (
    NonRetryableProviderError,
    RetryableProviderError,
)
from notification_service.domain.models import NotificationRequest, NotificationType, RequestStatus
from notification_service.infrastructure.rate_limiter import SlidingWindowRateLimiter
from notification_service.infrastructure.repositories import (
    InMemoryNotificationRequestRepository,
)
from notification_service.infrastructure.settings import Settings


class FakeProviderClient:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = deque(outcomes)
        self.calls = 0

    async def send_notification(self, notification_request: NotificationRequest) -> str:
        self.calls += 1
        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return str(outcome)

    async def close(self) -> None:
        return None


def build_settings(**overrides: object) -> Settings:
    base = Settings(
        worker_count=1,
        max_retry_attempts=3,
        base_backoff_seconds=0.0,
        max_backoff_seconds=0.0,
        rate_limit_max_calls=100,
        rate_limit_period_seconds=1.0,
    )
    return replace(base, **overrides)


async def wait_for_status(
    repository: InMemoryNotificationRequestRepository,
    request_id: str,
    expected_status: RequestStatus,
    timeout: float = 1.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        notification_request = await repository.require(request_id)
        if notification_request.status == expected_status:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Request {request_id} did not reach status {expected_status!s}.")


@pytest.mark.asyncio
async def test_processing_coordinator_sends_notification_successfully() -> None:
    repository = InMemoryNotificationRequestRepository()
    notification_request = await repository.create(
        NotificationRequest.create(
            to="user@example.com",
            message="Hello",
            notification_type=NotificationType.EMAIL,
        )
    )
    provider_client = FakeProviderClient(["provider-1"])
    coordinator = NotificationProcessingCoordinator(
        repository=repository,
        provider_client=provider_client,
        rate_limiter=SlidingWindowRateLimiter(max_calls=100, period_seconds=1.0),
        settings=build_settings(),
    )

    await coordinator.start()
    try:
        outcome = await coordinator.submit(notification_request.id)
        assert outcome == ProcessRequestOutcome.ENQUEUED

        await wait_for_status(repository, notification_request.id, RequestStatus.SENT)
        stored = await repository.require(notification_request.id)
        assert stored.provider_id == "provider-1"
        assert provider_client.calls == 1
    finally:
        await coordinator.stop()


@pytest.mark.asyncio
async def test_processing_coordinator_retries_transient_failures() -> None:
    repository = InMemoryNotificationRequestRepository()
    notification_request = await repository.create(
        NotificationRequest.create(
            to="user@example.com",
            message="Hello",
            notification_type=NotificationType.EMAIL,
        )
    )
    provider_client = FakeProviderClient(
        [RetryableProviderError("temporary"), "provider-2"]
    )
    coordinator = NotificationProcessingCoordinator(
        repository=repository,
        provider_client=provider_client,
        rate_limiter=SlidingWindowRateLimiter(max_calls=100, period_seconds=1.0),
        settings=build_settings(),
        sleep_func=lambda _: asyncio.sleep(0),
        jitter_func=lambda: 0.0,
    )

    await coordinator.start()
    try:
        await coordinator.submit(notification_request.id)
        await wait_for_status(repository, notification_request.id, RequestStatus.SENT)
        assert provider_client.calls == 2
    finally:
        await coordinator.stop()


@pytest.mark.asyncio
async def test_processing_coordinator_marks_request_failed_for_non_retryable_errors() -> None:
    repository = InMemoryNotificationRequestRepository()
    notification_request = await repository.create(
        NotificationRequest.create(
            to="user@example.com",
            message="Hello",
            notification_type=NotificationType.EMAIL,
        )
    )
    provider_client = FakeProviderClient([NonRetryableProviderError("bad request")])
    coordinator = NotificationProcessingCoordinator(
        repository=repository,
        provider_client=provider_client,
        rate_limiter=SlidingWindowRateLimiter(max_calls=100, period_seconds=1.0),
        settings=build_settings(),
    )

    await coordinator.start()
    try:
        await coordinator.submit(notification_request.id)
        await wait_for_status(repository, notification_request.id, RequestStatus.FAILED)
        stored = await repository.require(notification_request.id)
        assert stored.last_error == "bad request"
    finally:
        await coordinator.stop()


@pytest.mark.asyncio
async def test_processing_coordinator_requeues_failed_requests_without_duplicates() -> None:
    repository = InMemoryNotificationRequestRepository()
    notification_request = await repository.create(
        NotificationRequest.create(
            to="user@example.com",
            message="Hello",
            notification_type=NotificationType.PUSH,
        )
    )
    await repository.mark_failed(notification_request.id, "previous failure")

    provider_client = FakeProviderClient(["provider-3"])
    coordinator = NotificationProcessingCoordinator(
        repository=repository,
        provider_client=provider_client,
        rate_limiter=SlidingWindowRateLimiter(max_calls=100, period_seconds=1.0),
        settings=build_settings(),
    )

    await coordinator.start()
    try:
        first_outcome = await coordinator.submit(notification_request.id)
        second_outcome = await coordinator.submit(notification_request.id)

        assert first_outcome == ProcessRequestOutcome.ENQUEUED
        assert second_outcome == ProcessRequestOutcome.ALREADY_PROCESSING

        await wait_for_status(repository, notification_request.id, RequestStatus.SENT)
        assert provider_client.calls == 1
    finally:
        await coordinator.stop()
