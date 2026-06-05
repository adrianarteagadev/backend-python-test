from __future__ import annotations

import asyncio
from typing import Callable

from notification_service.domain.exceptions import RequestNotFoundError
from notification_service.domain.models import NotificationRequest


class InMemoryNotificationRequestRepository:
    def __init__(self) -> None:
        self._items: dict[str, NotificationRequest] = {}
        self._lock = asyncio.Lock()

    async def create(self, notification_request: NotificationRequest) -> NotificationRequest:
        async with self._lock:
            stored = notification_request.clone()
            self._items[stored.id] = stored
            return stored.clone()

    async def get(self, request_id: str) -> NotificationRequest | None:
        async with self._lock:
            stored = self._items.get(request_id)
            return stored.clone() if stored is not None else None

    async def require(self, request_id: str) -> NotificationRequest:
        async with self._lock:
            stored = self._items.get(request_id)
            if stored is None:
                raise RequestNotFoundError(f"Notification request '{request_id}' was not found.")
            return stored.clone()

    async def mark_queued(self, request_id: str) -> NotificationRequest:
        return await self._mutate(request_id, lambda item: item.mark_queued())

    async def mark_processing(self, request_id: str) -> NotificationRequest:
        return await self._mutate(request_id, lambda item: item.mark_processing())

    async def mark_sent(self, request_id: str, provider_id: str) -> NotificationRequest:
        return await self._mutate(request_id, lambda item: item.mark_sent(provider_id))

    async def mark_failed(self, request_id: str, error: str) -> NotificationRequest:
        return await self._mutate(request_id, lambda item: item.mark_failed(error))

    async def _mutate(
        self,
        request_id: str,
        updater: Callable[[NotificationRequest], None],
    ) -> NotificationRequest:
        async with self._lock:
            stored = self._items.get(request_id)
            if stored is None:
                raise RequestNotFoundError(f"Notification request '{request_id}' was not found.")
            updater(stored)
            return stored.clone()
