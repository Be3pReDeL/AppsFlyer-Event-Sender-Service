"""Tests for protected admin dev-key mapping endpoint."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Set environment for admin endpoint tests."""
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("ADMIN_TOKENS", "admin-test-token")
    monkeypatch.setenv("APPSFLYER_DEV_KEY_DB_PATH", str(tmp_path / "dev-keys.db"))


def test_upsert_dev_key_mapping_success(client: TestClient) -> None:
    """Admin endpoint should persist app_id -> dev_key mapping."""
    response = client.post(
        "/v1/admin/dev-keys",
        headers={"X-Admin-Token": "admin-test-token"},
        json={
            "app_id": "id123456789",
            "dev_key": "dev-key-abc",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    assert data["app_id"] == "id123456789"
    assert "updated_at" in data


def test_upsert_dev_key_mapping_requires_admin_token(client: TestClient) -> None:
    """Admin endpoint should reject missing auth header."""
    response = client.post(
        "/v1/admin/dev-keys",
        json={
            "app_id": "id123456789",
            "dev_key": "dev-key-abc",
        },
    )

    assert response.status_code == 401


def test_upsert_dev_key_mapping_persists_latest_value(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Upsert should overwrite previous dev key for the same app_id."""
    db_path = tmp_path / "dev-keys.db"

    first = client.post(
        "/v1/admin/dev-keys",
        headers={"X-Admin-Token": "admin-test-token"},
        json={
            "app_id": "id6758761140",
            "dev_key": "old-key",
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/v1/admin/dev-keys",
        headers={"X-Admin-Token": "admin-test-token"},
        json={
            "app_id": "id6758761140",
            "dev_key": "new-key",
        },
    )
    assert second.status_code == 200

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT dev_key FROM appsflyer_dev_keys WHERE app_id = ?",
            ("id6758761140",),
        ).fetchone()

    assert row is not None
    assert row[0] == "new-key"
