from typing import Annotated

from pydantic import BaseModel, StringConstraints

from notification_service.domain.models import NotificationType, RequestStatus


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateNotificationRequest(BaseModel):
    to: NonEmptyStr
    message: NonEmptyStr
    type: NotificationType


class CreateNotificationResponse(BaseModel):
    id: str


class GetNotificationResponse(BaseModel):
    id: str
    status: RequestStatus
