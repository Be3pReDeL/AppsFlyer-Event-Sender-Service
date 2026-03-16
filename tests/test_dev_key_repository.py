"""Tests for dev key repository backend selection."""

from unittest.mock import patch

import pytest

from app.appsflyer.dev_key_repository import DevKeyRepository


@pytest.mark.asyncio
async def test_repository_prefers_postgres_when_database_url_is_set() -> None:
    """Repository should use Postgres backend when database URL is configured."""
    repo = DevKeyRepository(
        database_url="postgresql://user:pass@localhost:5432/appsflyer",
        sqlite_db_path="/tmp/fallback.db",
    )

    with (
        patch.object(repo, "_init_postgres_db") as init_postgres,
        patch.object(repo, "_get_dev_key_postgres_sync", return_value="pg-dev-key") as get_postgres,
        patch.object(repo, "_get_dev_key_sqlite_sync", return_value="sqlite-dev-key") as get_sqlite,
    ):
        result = await repo.get_dev_key("id123456789")

    assert result == "pg-dev-key"
    init_postgres.assert_called_once_with()
    get_postgres.assert_called_once_with("id123456789")
    get_sqlite.assert_not_called()


@pytest.mark.asyncio
async def test_repository_prefers_postgres_for_upsert_when_database_url_is_set() -> None:
    """Repository should use Postgres upsert when database URL is configured."""
    repo = DevKeyRepository(
        database_url="postgresql://user:pass@localhost:5432/appsflyer",
        sqlite_db_path="/tmp/fallback.db",
    )

    with (
        patch.object(repo, "_init_postgres_db") as init_postgres,
        patch.object(
            repo,
            "_upsert_dev_key_postgres_sync",
            return_value="2026-03-16T10:00:00+00:00",
        ) as upsert_postgres,
        patch.object(repo, "_upsert_dev_key_sqlite_sync") as upsert_sqlite,
    ):
        updated_at = await repo.upsert_dev_key("id123456789", "pg-dev-key")

    assert updated_at == "2026-03-16T10:00:00+00:00"
    init_postgres.assert_called_once_with()
    upsert_postgres.assert_called_once_with("id123456789", "pg-dev-key")
    upsert_sqlite.assert_not_called()
