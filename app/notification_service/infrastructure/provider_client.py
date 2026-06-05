from __future__ import annotations

import json
from typing import Any

import httpx

from notification_service.domain.exceptions import (
    NonRetryableProviderError,
    RetryableProviderError,
)
from notification_service.domain.models import NotificationRequest
from notification_service.infrastructure.settings import Settings


class ProviderClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.provider_base_url,
            headers={
                "X-API-Key": settings.provider_api_key,
                "Content-Type": "application/json",
            },
            timeout=settings.provider_timeout_seconds,
            transport=transport,
        )

    async def send_notification(self, notification_request: NotificationRequest) -> str:
        payload = {
            "to": notification_request.to,
            "message": notification_request.message,
            "type": notification_request.type.value,
        }

        try:
            response = await self._client.post(
                "/v1/notify",
                json=payload,
                params={
                    "priority": "normal",
                    "trace_id": notification_request.id,
                },
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise RetryableProviderError(f"Provider communication error: {exc}") from exc

        if response.status_code == 200:
            body = response.json()
            provider_id = body.get("provider_id")
            if not provider_id:
                raise RetryableProviderError("Provider response did not include provider_id.")
            return str(provider_id)

        message = self._extract_error_message(response)
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableProviderError(message)
        raise NonRetryableProviderError(message)

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            body: Any = response.json()
        except (json.JSONDecodeError, ValueError):
            return response.text or f"Provider returned {response.status_code}."

        if isinstance(body, dict):
            return str(body.get("detail") or body.get("error") or body)
        return str(body)
