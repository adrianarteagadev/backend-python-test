from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NotificationType(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class RequestStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"


@dataclass(slots=True)
class NotificationRequest:
    id: str
    to: str
    message: str
    type: NotificationType
    status: RequestStatus = RequestStatus.QUEUED
    provider_id: str | None = None
    last_error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        to: str,
        message: str,
        notification_type: NotificationType,
    ) -> "NotificationRequest":
        return cls(
            id=str(uuid4()),
            to=to,
            message=message,
            type=notification_type,
        )

    def clone(self) -> "NotificationRequest":
        return replace(self)

    def mark_queued(self) -> None:
        self.status = RequestStatus.QUEUED
        self.provider_id = None
        self.last_error = None
        self._touch()

    def mark_processing(self) -> None:
        self.status = RequestStatus.PROCESSING
        self.last_error = None
        self._touch()

    def mark_sent(self, provider_id: str) -> None:
        self.status = RequestStatus.SENT
        self.provider_id = provider_id
        self.last_error = None
        self._touch()

    def mark_failed(self, error: str) -> None:
        self.status = RequestStatus.FAILED
        self.last_error = error
        self._touch()

    def _touch(self) -> None:
        self.updated_at = utc_now()
