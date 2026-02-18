"""Tests for handling Redis unavailability."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_tracking_endpoint_redis_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that tracking endpoints return 503 when Redis is unavailable."""
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("API_TOKENS", "test-token")

    # Create client and simulate Redis failure by setting app.state.redis to None
    client = TestClient(app)
    client.app.state.redis = None

    # Mock producer to prevent it from being called
    with patch("app.api.routes.get_producer") as mock:
        producer = AsyncMock()
        mock.return_value = producer

        # Try to track registration
        response = client.get(
            "/v1/track/registration",
            params={"token": "test-token", "appsflyer_id": "device-123"},
        )

        # Should return 503 Service Unavailable
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

        # Producer should not have been called since _get_redis raised exception
        producer.enqueue.assert_not_called()


def test_tracking_endpoint_redis_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that tracking endpoints work when Redis is available."""
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("API_TOKENS", "test-token")

    client = TestClient(app)

    # Simulate Redis being available
    mock_redis = AsyncMock()
    client.app.state.redis = mock_redis

    with patch("app.api.routes.get_producer") as mock:
        producer = AsyncMock()
        producer.check_duplicate.return_value = False
        producer.enqueue.return_value = "msg-id"
        producer.mark_processed.return_value = None
        mock.return_value = producer

        response = client.get(
            "/v1/track/registration",
            params={"token": "test-token", "appsflyer_id": "device-123"},
        )

        # Should succeed
        assert response.status_code == 202
        assert response.json()["status"] == "accepted"

        # Producer should have been called
        producer.enqueue.assert_called_once()
