"""Tests for health check endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


def test_liveness_endpoint(client: TestClient) -> None:
    """Test that liveness endpoint returns OK."""
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "service" in data
    assert "version" in data


def test_readiness_endpoint_redis_available(client: TestClient) -> None:
    """Test readiness endpoint when Redis is available."""
    with patch("app.api.health._check_redis", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = True
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["checks"]["redis"] is True


def test_readiness_endpoint_redis_unavailable(client: TestClient) -> None:
    """Test readiness endpoint when Redis is unavailable."""
    with patch("app.api.health._check_redis", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = False
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["status"] == "unhealthy"
        assert data["detail"]["checks"]["redis"] is False
