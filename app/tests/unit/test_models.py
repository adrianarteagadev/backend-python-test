from notification_service.domain.models import (
    NotificationRequest,
    NotificationType,
    RequestStatus,
)


def test_notification_request_starts_queued() -> None:
    notification_request = NotificationRequest.create(
        to="user@example.com",
        message="Hello",
        notification_type=NotificationType.EMAIL,
    )

    assert notification_request.id
    assert notification_request.status == RequestStatus.QUEUED
    assert notification_request.provider_id is None
    assert notification_request.last_error is None


def test_notification_request_transitions_are_consistent() -> None:
    notification_request = NotificationRequest.create(
        to="user@example.com",
        message="Hello",
        notification_type=NotificationType.SMS,
    )

    notification_request.mark_processing()
    assert notification_request.status == RequestStatus.PROCESSING

    notification_request.mark_failed("temporary failure")
    assert notification_request.status == RequestStatus.FAILED
    assert notification_request.last_error == "temporary failure"

    notification_request.mark_queued()
    assert notification_request.status == RequestStatus.QUEUED
    assert notification_request.last_error is None

    notification_request.mark_sent("provider-123")
    assert notification_request.status == RequestStatus.SENT
    assert notification_request.provider_id == "provider-123"
    assert notification_request.last_error is None
