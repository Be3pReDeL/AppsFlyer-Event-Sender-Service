"""Tests for tracking API routes."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up token auth for all tests."""
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("API_TOKENS", "test-token")


@pytest.fixture(autouse=True)
def mock_redis_and_producer(client: TestClient) -> None:
    """Mock Redis and EventProducer for all tests."""
    # Mock Redis in app.state
    mock_redis = AsyncMock()
    client.app.state.redis = mock_redis

    # Mock EventProducer
    with patch("app.api.routes.get_producer") as mock:
        producer = AsyncMock()
        producer.check_duplicate.return_value = False
        producer.enqueue.return_value = "msg-id-123"
        producer.mark_processed.return_value = None
        mock.return_value = producer
        yield producer


def test_registration_get_minimal(client: TestClient) -> None:
    """Test registration GET endpoint with minimal parameters."""
    response = client.get(
        "/v1/track/registration",
        params={"token": "test-token", "appsflyer_id": "device-123"},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert "event_id" in data
    assert data["event_id"].startswith("reg_")
    assert "queued_at" in data


def test_registration_get_full_parameters(client: TestClient) -> None:
    """Test registration GET endpoint with all parameters."""
    response = client.get(
        "/v1/track/registration",
        params={
            "token": "test-token",
            "appsflyer_id": "device-123",
            "customer_user_id": "user-456",
            "device_id": "ios-device-789",
            "platform": "ios",
            "registration_method": "email",
            "event_id": "custom_event_id_123",
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["event_id"] == "custom_event_id_123"


def test_registration_post_query_params(client: TestClient) -> None:
    """Test registration POST endpoint with query parameters (Keitaro-compatible)."""
    response = client.post(
        "/v1/track/registration",
        params={
            "token": "test-token",
            "appsflyer_id": "device-123",
            "customer_user_id": "user-456",
            "platform": "android",
            "registration_method": "social",
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert "event_id" in data


def test_registration_post_dev_key_is_stored_in_payload(
    client: TestClient,
    mock_redis_and_producer: AsyncMock,
) -> None:
    """Test that dev_key query parameter is propagated to worker payload."""
    response = client.post(
        "/v1/track/registration",
        params={
            "token": "test-token",
            "appsflyer_id": "device-123",
            "dev_key": "request-dev-key-123",
        },
    )

    assert response.status_code == 202
    assert mock_redis_and_producer.enqueue.called
    enqueued_event = mock_redis_and_producer.enqueue.call_args.args[0]
    assert enqueued_event.payload["dev_key"] == "request-dev-key-123"


def test_purchase_get_minimal(client: TestClient) -> None:
    """Test purchase GET endpoint with required parameters."""
    response = client.get(
        "/v1/track/purchase",
        params={
            "token": "test-token",
            "revenue": 9.99,
            "currency": "USD",
            "appsflyer_id": "device-123",
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert "event_id" in data
    assert data["event_id"].startswith("purchase_")


def test_purchase_get_missing_revenue(client: TestClient) -> None:
    """Test that purchase without revenue returns 400."""
    response = client.get(
        "/v1/track/purchase",
        params={
            "token": "test-token",
            "currency": "USD",
        },
    )

    assert response.status_code == 400
    assert "required" in response.json()["error"].lower()


def test_purchase_get_missing_currency(client: TestClient) -> None:
    """Test that purchase without currency returns 400."""
    response = client.get(
        "/v1/track/purchase",
        params={
            "token": "test-token",
            "revenue": 9.99,
        },
    )

    assert response.status_code == 400
    assert "required" in response.json()["error"].lower()


def test_registration_proxy_post_allows_hmac_mode(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proxy endpoint should accept token auth even when AUTH_MODE=hmac."""
    monkeypatch.setenv("AUTH_MODE", "hmac")
    monkeypatch.setenv("HMAC_KEYS_JSON", "{\"keitaro\":\"secret\"}")

    response = client.post(
        "/v1/track/registration/proxy",
        params={
            "token": "test-token",
            "appsflyer_id": "device-123",
            "platform": "ios",
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert "event_id" in data


def test_purchase_proxy_post_allows_hmac_mode(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proxy purchase endpoint should accept token auth in HMAC mode."""
    monkeypatch.setenv("AUTH_MODE", "hmac")
    monkeypatch.setenv("HMAC_KEYS_JSON", "{\"keitaro\":\"secret\"}")

    response = client.post(
        "/v1/track/purchase/proxy",
        params={
            "token": "test-token",
            "appsflyer_id": "device-123",
            "revenue": 19.99,
            "currency": "USD",
            "platform": "android",
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["event_id"].startswith("purchase_")


def test_purchase_post_query_params(client: TestClient) -> None:
    """Test purchase POST endpoint with query parameters (Keitaro-compatible)."""
    response = client.post(
        "/v1/track/purchase",
        params={
            "token": "test-token",
            "revenue": 19.99,
            "currency": "EUR",
            "appsflyer_id": "device-123",
            "customer_user_id": "user-456",
            "platform": "ios",
            "product_id": "premium_yearly",
            "order_id": "order_abc123",
            "quantity": 1,
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"


def test_purchase_post_invalid_revenue(client: TestClient) -> None:
    """Test that negative revenue returns validation error."""
    response = client.post(
        "/v1/track/purchase",
        params={
            "token": "test-token",
            "revenue": -10.0,
            "currency": "USD",
            "appsflyer_id": "device-123",
        },
    )

    assert response.status_code == 422  # Pydantic validation error


def test_purchase_post_invalid_currency(client: TestClient) -> None:
    """Test that invalid currency format returns validation error."""
    response = client.post(
        "/v1/track/purchase",
        params={
            "token": "test-token",
            "revenue": 10.0,
            "currency": "US",  # Too short
            "appsflyer_id": "device-123",
        },
    )

    assert response.status_code == 422  # Pydantic validation error


def test_registration_without_auth(client: TestClient) -> None:
    """Test that request without auth returns 401."""
    response = client.get(
        "/v1/track/registration",
        params={"appsflyer_id": "device-123"},
    )

    assert response.status_code == 401


def test_purchase_without_auth(client: TestClient) -> None:
    """Test that request without auth returns 401."""
    response = client.get(
        "/v1/track/purchase",
        params={"revenue": 9.99, "currency": "USD"},
    )

    assert response.status_code == 401


def test_event_id_deduplication_preserves_custom_id(client: TestClient) -> None:
    """Test that custom event_id is preserved."""
    custom_id = "my_custom_event_12345"

    response = client.get(
        "/v1/track/registration",
        params={
            "token": "test-token",
            "appsflyer_id": "device-123",
            "event_id": custom_id,
        },
    )

    assert response.status_code == 202
    assert response.json()["event_id"] == custom_id
