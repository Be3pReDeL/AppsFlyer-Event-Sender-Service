"""Tests for authentication module."""

import hashlib
import hmac
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client_with_token() -> TestClient:
    """Create a test client with token auth configured."""
    return TestClient(app)


def test_token_auth_missing_token(client_with_token: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing token returns 401."""
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("API_TOKENS", "test-token-123")

    response = client_with_token.get("/v1/track/registration")
    assert response.status_code == 401
    assert "Missing token" in response.json()["error"]


def test_token_auth_invalid_token(client_with_token: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that invalid token returns 401."""
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("API_TOKENS", "valid-token-123")

    response = client_with_token.get("/v1/track/registration?token=invalid-token")
    assert response.status_code == 401
    assert "Invalid token" in response.json()["error"]


def test_token_auth_valid_token(client_with_token: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that valid token passes authentication."""
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("API_TOKENS", "valid-token-123,another-token")

    response = client_with_token.get(
        "/v1/track/registration",
        params={"token": "valid-token-123", "appsflyer_id": "test-device-id"},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert "event_id" in data


def test_token_auth_multiple_tokens(client_with_token: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that any of multiple configured tokens work."""
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("API_TOKENS", "token1,token2,token3")

    # Test each token
    for token in ["token1", "token2", "token3"]:
        response = client_with_token.get(
            "/v1/track/registration",
            params={"token": token, "appsflyer_id": "test-device-id"},
        )
        assert response.status_code == 202


def test_hmac_auth_missing_parameters(client_with_token: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing HMAC parameters return 401."""
    monkeypatch.setenv("AUTH_MODE", "hmac")
    monkeypatch.setenv("HMAC_KEYS_JSON", '{"test-key": "test-secret"}')

    # Missing all HMAC params
    response = client_with_token.get("/v1/track/registration")
    assert response.status_code == 401
    assert "HMAC" in response.json()["error"]


def test_hmac_auth_invalid_key(client_with_token: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that invalid HMAC key returns 401."""
    monkeypatch.setenv("AUTH_MODE", "hmac")
    monkeypatch.setenv("HMAC_KEYS_JSON", '{"valid-key": "secret123"}')

    ts = str(int(time.time()))
    response = client_with_token.get(
        "/v1/track/registration",
        params={
            "key": "invalid-key",
            "ts": ts,
            "sig": "dummy-signature",
        },
    )
    assert response.status_code == 401
    assert "Invalid key" in response.json()["error"]


def test_hmac_auth_expired_timestamp(client_with_token: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that expired timestamp returns 401."""
    monkeypatch.setenv("AUTH_MODE", "hmac")
    monkeypatch.setenv("HMAC_KEYS_JSON", '{"test-key": "secret123"}')
    monkeypatch.setenv("AUTH_TS_SKEW_SECONDS", "300")

    # Timestamp from 1 hour ago
    old_ts = str(int(time.time()) - 3600)

    response = client_with_token.get(
        "/v1/track/registration",
        params={
            "key": "test-key",
            "ts": old_ts,
            "sig": "dummy-signature",
        },
    )
    assert response.status_code == 401
    assert "Timestamp" in response.json()["error"]


def test_hmac_auth_valid_signature(client_with_token: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that valid HMAC signature passes authentication."""
    monkeypatch.setenv("AUTH_MODE", "hmac")
    monkeypatch.setenv("HMAC_KEYS_JSON", '{"test-key": "secret123"}')

    # Generate valid HMAC
    key = "test-key"
    secret = "secret123"
    ts = str(int(time.time()))
    appsflyer_id = "device-123"

    # Build canonical query (sorted, excluding sig)
    params = {
        "appsflyer_id": appsflyer_id,
        "key": key,
        "ts": ts,
    }
    canonical_query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))

    # Compute signature (canonical_query already contains ts)
    message = canonical_query.encode()
    sig = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    # Make request
    response = client_with_token.get(
        "/v1/track/registration",
        params={
            "key": key,
            "ts": ts,
            "sig": sig,
            "appsflyer_id": appsflyer_id,
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
