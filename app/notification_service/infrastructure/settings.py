from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "Notification Service (Technical Test)"
    provider_base_url: str = "http://localhost:3001"
    provider_api_key: str = "test-dev-2026"
    provider_timeout_seconds: float = 2.0
    worker_count: int = 8
    max_retry_attempts: int = 5
    base_backoff_seconds: float = 0.2
    max_backoff_seconds: float = 2.0
    rate_limit_max_calls: int = 45
    rate_limit_period_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        default_workers = max(4, min(16, (os.cpu_count() or 4) * 2))
        return cls(
            app_name=os.getenv("APP_NAME", defaults.app_name),
            provider_base_url=os.getenv("PROVIDER_BASE_URL", defaults.provider_base_url),
            provider_api_key=os.getenv("PROVIDER_API_KEY", defaults.provider_api_key),
            provider_timeout_seconds=float(
                os.getenv("PROVIDER_TIMEOUT_SECONDS", defaults.provider_timeout_seconds)
            ),
            worker_count=int(os.getenv("WORKER_COUNT", default_workers)),
            max_retry_attempts=int(
                os.getenv("MAX_RETRY_ATTEMPTS", defaults.max_retry_attempts)
            ),
            base_backoff_seconds=float(
                os.getenv("BASE_BACKOFF_SECONDS", defaults.base_backoff_seconds)
            ),
            max_backoff_seconds=float(
                os.getenv("MAX_BACKOFF_SECONDS", defaults.max_backoff_seconds)
            ),
            rate_limit_max_calls=int(
                os.getenv("RATE_LIMIT_MAX_CALLS", defaults.rate_limit_max_calls)
            ),
            rate_limit_period_seconds=float(
                os.getenv(
                    "RATE_LIMIT_PERIOD_SECONDS",
                    defaults.rate_limit_period_seconds,
                )
            ),
        )
