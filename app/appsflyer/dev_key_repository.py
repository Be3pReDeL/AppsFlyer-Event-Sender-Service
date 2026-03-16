"""Persistent app_id -> dev_key mapping repository."""

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


class DevKeyRepository:
    """Repository for storing per-app AppsFlyer dev keys."""

    def __init__(
        self,
        database_url: str = "",
        sqlite_db_path: str = "/data/appsflyer_dev_keys.db",
    ) -> None:
        self.database_url = database_url.strip()
        self.sqlite_db_path = sqlite_db_path
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize schema once per process."""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return
            init_db = self._init_postgres_db if self._uses_postgres() else self._init_sqlite_db
            await asyncio.to_thread(init_db)
            self._initialized = True

    def _uses_postgres(self) -> bool:
        return bool(self.database_url)

    def _connect_sqlite(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_db_path, timeout=5.0)
        # WAL improves concurrent read/write behavior for API + worker processes.
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _connect_postgres(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "psycopg must be installed when APPSFLYER_DEV_KEY_DATABASE_URL is configured"
            ) from exc

        # Use a short-lived connection per operation to avoid cross-thread sharing.
        return psycopg.connect(self.database_url, autocommit=True)

    def _init_sqlite_db(self) -> None:
        Path(self.sqlite_db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._connect_sqlite() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS appsflyer_dev_keys (
                    app_id TEXT PRIMARY KEY,
                    dev_key TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _init_postgres_db(self) -> None:
        with self._connect_postgres() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS appsflyer_dev_keys (
                    app_id TEXT PRIMARY KEY,
                    dev_key TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                )
                """
            )

    async def upsert_dev_key(self, app_id: str, dev_key: str) -> str:
        """Insert or update dev key for app_id.

        Returns:
            ISO timestamp of update in UTC.
        """
        await self.initialize()
        upsert_dev_key = (
            self._upsert_dev_key_postgres_sync
            if self._uses_postgres()
            else self._upsert_dev_key_sqlite_sync
        )
        return await asyncio.to_thread(upsert_dev_key, app_id, dev_key)

    def _upsert_dev_key_sqlite_sync(self, app_id: str, dev_key: str) -> str:
        updated_at = datetime.now(timezone.utc).isoformat()

        with self._connect_sqlite() as conn:
            conn.execute(
                """
                INSERT INTO appsflyer_dev_keys (app_id, dev_key, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(app_id) DO UPDATE SET
                    dev_key = excluded.dev_key,
                    updated_at = excluded.updated_at
                """,
                (app_id, dev_key, updated_at),
            )
            conn.commit()

        logger.info("dev_key_mapping_upserted", app_id=app_id)
        return updated_at

    def _upsert_dev_key_postgres_sync(self, app_id: str, dev_key: str) -> str:
        updated_at = datetime.now(timezone.utc)

        with self._connect_postgres() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO appsflyer_dev_keys (app_id, dev_key, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT(app_id) DO UPDATE SET
                    dev_key = EXCLUDED.dev_key,
                    updated_at = EXCLUDED.updated_at
                """,
                (app_id, dev_key, updated_at),
            )

        logger.info("dev_key_mapping_upserted", app_id=app_id)
        return updated_at.isoformat()

    async def get_dev_key(self, app_id: str) -> str | None:
        """Get dev key for app_id if present."""
        await self.initialize()
        get_dev_key = self._get_dev_key_postgres_sync if self._uses_postgres() else self._get_dev_key_sqlite_sync
        return await asyncio.to_thread(get_dev_key, app_id)

    def _get_dev_key_sqlite_sync(self, app_id: str) -> str | None:
        with self._connect_sqlite() as conn:
            cursor = conn.execute(
                "SELECT dev_key FROM appsflyer_dev_keys WHERE app_id = ?",
                (app_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def _get_dev_key_postgres_sync(self, app_id: str) -> str | None:
        with self._connect_postgres() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT dev_key FROM appsflyer_dev_keys WHERE app_id = %s",
                (app_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None
