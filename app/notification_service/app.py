from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI

from notification_service.api.routes import router
from notification_service.application.processing import NotificationProcessingCoordinator
from notification_service.application.services import NotificationApplicationService
from notification_service.infrastructure.logging import configure_logging
from notification_service.infrastructure.provider_client import ProviderClient
from notification_service.infrastructure.rate_limiter import SlidingWindowRateLimiter
from notification_service.infrastructure.repositories import (
    InMemoryNotificationRequestRepository,
)
from notification_service.infrastructure.settings import Settings


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    repository: InMemoryNotificationRequestRepository
    application_service: NotificationApplicationService
    processor: NotificationProcessingCoordinator


def build_container(
    settings: Settings,
    *,
    provider_transport: httpx.AsyncBaseTransport | None = None,
) -> ServiceContainer:
    repository = InMemoryNotificationRequestRepository()
    provider_client = ProviderClient(settings, transport=provider_transport)
    rate_limiter = SlidingWindowRateLimiter(
        max_calls=settings.rate_limit_max_calls,
        period_seconds=settings.rate_limit_period_seconds,
    )
    processor = NotificationProcessingCoordinator(
        repository=repository,
        provider_client=provider_client,
        rate_limiter=rate_limiter,
        settings=settings,
    )
    application_service = NotificationApplicationService(
        repository=repository,
        processor=processor,
    )
    return ServiceContainer(
        settings=settings,
        repository=repository,
        application_service=application_service,
        processor=processor,
    )


def create_app(
    settings: Settings | None = None,
    *,
    provider_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    configure_logging()
    resolved_settings = settings or Settings.from_env()
    container = build_container(
        resolved_settings,
        provider_transport=provider_transport,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = container
        app.state.notification_service = container.application_service
        await container.processor.start()
        yield
        await container.processor.stop()

    app = FastAPI(
        title=resolved_settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app
