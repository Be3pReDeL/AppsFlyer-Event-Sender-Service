"""Tests for tracking API routes."""

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


def test_registration_post_json(client: TestClient) -> None:
    """Test registration POST endpoint with JSON body."""
    response = client.post(
        "/v1/track/registration?token=test-token",
        json={
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


def test_purchase_post_json(client: TestClient) -> None:
    """Test purchase POST endpoint with JSON body."""
    response = client.post(
        "/v1/track/purchase?token=test-token",
        json={
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
        "/v1/track/purchase?token=test-token",
        json={
            "revenue": -10.0,
            "currency": "USD",
            "appsflyer_id": "device-123",
        },
    )

    assert response.status_code == 422  # Pydantic validation error


def test_purchase_post_invalid_currency(client: TestClient) -> None:
    """Test that invalid currency format returns validation error."""
    response = client.post(
        "/v1/track/purchase?token=test-token",
        json={
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
