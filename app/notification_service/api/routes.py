from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from notification_service.api.schemas import (
    CreateNotificationRequest,
    CreateNotificationResponse,
    GetNotificationResponse,
)
from notification_service.application.services import NotificationApplicationService
from notification_service.application.types import ProcessRequestOutcome
from notification_service.domain.exceptions import RequestNotFoundError

router = APIRouter(prefix="/v1/requests", tags=["Notification Requests"])


def get_service(request: Request) -> NotificationApplicationService:
    return request.app.state.notification_service


@router.post(
    "",
    response_model=CreateNotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_request(
    payload: CreateNotificationRequest,
    service: NotificationApplicationService = Depends(get_service),
) -> CreateNotificationResponse:
    notification_request = await service.create_request(
        to=payload.to,
        message=payload.message,
        notification_type=payload.type,
    )
    return CreateNotificationResponse(id=notification_request.id)


@router.post(
    "/{request_id}/process",
    responses={
        200: {"description": "The request was already sent."},
        202: {"description": "The request was accepted for asynchronous processing."},
        404: {"description": "Notification request not found."},
    },
)
async def process_request(
    request_id: str,
    service: NotificationApplicationService = Depends(get_service),
) -> Response:
    try:
        outcome = await service.process_request(request_id)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if outcome == ProcessRequestOutcome.ALREADY_SENT:
        return Response(status_code=status.HTTP_200_OK)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get(
    "/{request_id}",
    response_model=GetNotificationResponse,
)
async def get_request(
    request_id: str,
    service: NotificationApplicationService = Depends(get_service),
) -> GetNotificationResponse:
    try:
        notification_request = await service.get_request(request_id)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return GetNotificationResponse(id=notification_request.id, status=notification_request.status)
