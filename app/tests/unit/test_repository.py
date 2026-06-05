import pytest

from notification_service.domain.exceptions import RequestNotFoundError
from notification_service.domain.models import (
    NotificationRequest,
    NotificationType,
    RequestStatus,
)
from notification_service.infrastructure.repositories import (
    InMemoryNotificationRequestRepository,
)


@pytest.mark.asyncio
async def test_repository_returns_clones_and_keeps_internal_state_safe() -> None:
    repository = InMemoryNotificationRequestRepository()
    created = await repository.create(
        NotificationRequest.create(
            to="user@example.com",
            message="Hello",
            notification_type=NotificationType.EMAIL,
        )
    )

    loaded = await repository.require(created.id)
    loaded.mark_failed("mutated outside repository")

    stored_again = await repository.require(created.id)
    assert stored_again.status == RequestStatus.QUEUED
    assert stored_again.last_error is None


@pytest.mark.asyncio
async def test_repository_updates_request_status() -> None:
    repository = InMemoryNotificationRequestRepository()
    created = await repository.create(
        NotificationRequest.create(
            to="user@example.com",
            message="Hello",
            notification_type=NotificationType.PUSH,
        )
    )

    await repository.mark_processing(created.id)
    processing = await repository.require(created.id)
    assert processing.status == RequestStatus.PROCESSING

    await repository.mark_sent(created.id, "provider-123")
    sent = await repository.require(created.id)
    assert sent.status == RequestStatus.SENT
    assert sent.provider_id == "provider-123"


@pytest.mark.asyncio
async def test_repository_raises_when_request_does_not_exist() -> None:
    repository = InMemoryNotificationRequestRepository()

    with pytest.raises(RequestNotFoundError):
        await repository.require("missing-id")
