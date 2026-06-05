import time
from collections import deque

import httpx
from fastapi.testclient import TestClient

from notification_service.app import create_app
from notification_service.infrastructure.settings import Settings


def build_test_client(
    handler,
    *,
    settings: Settings | None = None,
) -> TestClient:
    resolved_settings = settings or Settings(
        worker_count=2,
        max_retry_attempts=3,
        base_backoff_seconds=0.01,
        max_backoff_seconds=0.01,
        rate_limit_max_calls=100,
        rate_limit_period_seconds=1.0,
    )
    transport = httpx.MockTransport(handler)
    app = create_app(settings=resolved_settings, provider_transport=transport)
    return TestClient(app)


def wait_for_status(
    client: TestClient,
    request_id: str,
    *,
    expected: set[str],
    timeout: float = 1.0,
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/v1/requests/{request_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in expected:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"Request {request_id} did not reach one of {expected}.")


def test_create_process_and_get_request_successfully() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"status": "delivered", "provider_id": "provider-1"})

    with build_test_client(handler) as client:
        create_response = client.post(
            "/v1/requests",
            json={
                "to": "user@example.com",
                "message": "Hello",
                "type": "email",
            },
        )

        assert create_response.status_code == 201
        request_id = create_response.json()["id"]

        process_response = client.post(f"/v1/requests/{request_id}/process")
        assert process_response.status_code == 202

        status_payload = wait_for_status(client, request_id, expected={"sent"})
        assert status_payload == {"id": request_id, "status": "sent"}
        assert captured_requests[0].headers["X-API-Key"] == "test-dev-2026"


def test_process_retries_provider_transient_errors_until_sent() -> None:
    responses = deque(
        [
            httpx.Response(500, json={"detail": "temporary error"}),
            httpx.Response(200, json={"status": "delivered", "provider_id": "provider-2"}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.popleft()

    with build_test_client(handler) as client:
        request_id = client.post(
            "/v1/requests",
            json={"to": "user@example.com", "message": "Retry me", "type": "sms"},
        ).json()["id"]

        assert client.post(f"/v1/requests/{request_id}/process").status_code == 202
        wait_for_status(client, request_id, expected={"sent"})
        assert not responses


def test_process_marks_request_failed_after_retry_exhaustion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "rate limited"})

    with build_test_client(
        handler,
        settings=Settings(
            worker_count=1,
            max_retry_attempts=2,
            base_backoff_seconds=0.01,
            max_backoff_seconds=0.01,
            rate_limit_max_calls=100,
            rate_limit_period_seconds=1.0,
        ),
    ) as client:
        request_id = client.post(
            "/v1/requests",
            json={"to": "user@example.com", "message": "Fail me", "type": "push"},
        ).json()["id"]

        assert client.post(f"/v1/requests/{request_id}/process").status_code == 202
        payload = wait_for_status(client, request_id, expected={"failed"})
        assert payload["status"] == "failed"


def test_process_is_idempotent_while_request_is_being_processed() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        time.sleep(0.05)
        return httpx.Response(200, json={"status": "delivered", "provider_id": "provider-3"})

    with build_test_client(handler) as client:
        request_id = client.post(
            "/v1/requests",
            json={"to": "user@example.com", "message": "Hello", "type": "email"},
        ).json()["id"]

        first_process = client.post(f"/v1/requests/{request_id}/process")
        second_process = client.post(f"/v1/requests/{request_id}/process")

        assert first_process.status_code == 202
        assert second_process.status_code in {200, 202}
        wait_for_status(client, request_id, expected={"sent"})
        assert calls == 1


def test_validation_and_not_found_errors_are_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "delivered", "provider_id": "provider-4"})

    with build_test_client(handler) as client:
        invalid_create = client.post(
            "/v1/requests",
            json={"to": " ", "message": "", "type": "email"},
        )
        assert invalid_create.status_code == 422

        missing_get = client.get("/v1/requests/missing-id")
        missing_process = client.post("/v1/requests/missing-id/process")

        assert missing_get.status_code == 404
        assert missing_process.status_code == 404
