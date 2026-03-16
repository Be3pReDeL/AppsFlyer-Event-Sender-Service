"""Persistent app_id -> dev_key mapping repository (SQLite)."""

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


class DevKeyRepository:
    """Repository for storing per-app AppsFlyer dev keys."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize schema once per process."""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._init_db)
            self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        # WAL improves concurrent read/write behavior for API + worker processes.
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
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

    async def upsert_dev_key(self, app_id: str, dev_key: str) -> str:
        """Insert or update dev key for app_id.

        Returns:
            ISO timestamp of update in UTC.
        """
        await self.initialize()
        return await asyncio.to_thread(self._upsert_dev_key_sync, app_id, dev_key)

    def _upsert_dev_key_sync(self, app_id: str, dev_key: str) -> str:
        updated_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
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

    async def get_dev_key(self, app_id: str) -> str | None:
        """Get dev key for app_id if present."""
        await self.initialize()
        return await asyncio.to_thread(self._get_dev_key_sync, app_id)

    def _get_dev_key_sync(self, app_id: str) -> str | None:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT dev_key FROM appsflyer_dev_keys WHERE app_id = ?",
                (app_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None
