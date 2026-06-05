from notification_service.application.processing import NotificationProcessingCoordinator
from notification_service.application.types import ProcessRequestOutcome
from notification_service.domain.models import NotificationRequest, NotificationType
from notification_service.infrastructure.repositories import (
    InMemoryNotificationRequestRepository,
)


class NotificationApplicationService:
    def __init__(
        self,
        repository: InMemoryNotificationRequestRepository,
        processor: NotificationProcessingCoordinator,
    ) -> None:
        self._repository = repository
        self._processor = processor

    async def create_request(
        self,
        to: str,
        message: str,
        notification_type: NotificationType,
    ) -> NotificationRequest:
        notification_request = NotificationRequest.create(
            to=to,
            message=message,
            notification_type=notification_type,
        )
        return await self._repository.create(notification_request)

    async def get_request(self, request_id: str) -> NotificationRequest:
        return await self._repository.require(request_id)

    async def process_request(self, request_id: str) -> ProcessRequestOutcome:
        return await self._processor.submit(request_id)
