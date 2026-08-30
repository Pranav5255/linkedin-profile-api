from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA_VERSION = 1

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS profile_cache (
    public_identifier TEXT PRIMARY KEY,
    response_json TEXT NOT NULL,
    visibility TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS identity_cache (
    public_identifier TEXT PRIMARY KEY,
    entity_urn TEXT NOT NULL,
    visibility TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS query_registry (
    operation_name TEXT PRIMARY KEY,
    query_id TEXT,
    decoration_id TEXT,
    discovered_at TEXT,
    source_asset TEXT,
    last_success_at TEXT
);

CREATE TABLE IF NOT EXISTS session_state (
    slot TEXT PRIMARY KEY,
    last_outcome TEXT NOT NULL,
    last_outcome_at TEXT NOT NULL
);
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class CacheStore:
    def __init__(self, path: Path, ttl_seconds: int) -> None:
        self._path = path
        self._ttl_seconds = ttl_seconds
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_DDL)
        await self._db.commit()
        await self.purge_expired()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _require(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Cache is not open.")
        return self._db

    async def ready(self) -> bool:
        try:
            db = self._require()
            await db.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def purge_expired(self) -> None:
        db = self._require()
        now = _iso(_utc_now())
        await db.execute("DELETE FROM profile_cache WHERE expires_at < ?", (now,))
        await db.execute("DELETE FROM identity_cache WHERE expires_at < ?", (now,))
        await db.commit()

    async def get_profile(self, public_identifier: str) -> dict[str, Any] | None:
        db = self._require()
        cursor = await db.execute(
            """
            SELECT response_json, expires_at, schema_version
            FROM profile_cache
            WHERE public_identifier = ?
            """,
            (public_identifier,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        if row["schema_version"] != SCHEMA_VERSION:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= _utc_now():
            return None
        return json.loads(row["response_json"])

    async def put_profile(
        self,
        public_identifier: str,
        payload: dict[str, Any],
        visibility: str,
    ) -> None:
        db = self._require()
        now = _utc_now()
        expires = now + timedelta(seconds=self._ttl_seconds)
        await db.execute(
            """
            INSERT INTO profile_cache (
                public_identifier, response_json, visibility, fetched_at, expires_at, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(public_identifier) DO UPDATE SET
                response_json = excluded.response_json,
                visibility = excluded.visibility,
                fetched_at = excluded.fetched_at,
                expires_at = excluded.expires_at,
                schema_version = excluded.schema_version
            """,
            (
                public_identifier,
                json.dumps(payload, default=str),
                visibility,
                _iso(now),
                _iso(expires),
                SCHEMA_VERSION,
            ),
        )
        await db.commit()

    async def get_identity(self, public_identifier: str) -> dict[str, Any] | None:
        db = self._require()
        cursor = await db.execute(
            """
            SELECT entity_urn, visibility, expires_at
            FROM identity_cache
            WHERE public_identifier = ?
            """,
            (public_identifier,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= _utc_now():
            return None
        return {"entity_urn": row["entity_urn"], "visibility": row["visibility"]}

    async def put_identity(
        self,
        public_identifier: str,
        entity_urn: str,
        visibility: str,
    ) -> None:
        db = self._require()
        now = _utc_now()
        expires = now + timedelta(seconds=self._ttl_seconds)
        await db.execute(
            """
            INSERT INTO identity_cache (
                public_identifier, entity_urn, visibility, fetched_at, expires_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(public_identifier) DO UPDATE SET
                entity_urn = excluded.entity_urn,
                visibility = excluded.visibility,
                fetched_at = excluded.fetched_at,
                expires_at = excluded.expires_at
            """,
            (public_identifier, entity_urn, visibility, _iso(now), _iso(expires)),
        )
        await db.commit()

    async def get_query(self, operation_name: str) -> dict[str, Any] | None:
        db = self._require()
        cursor = await db.execute(
            """
            SELECT operation_name, query_id, decoration_id, discovered_at, source_asset, last_success_at
            FROM query_registry
            WHERE operation_name = ?
            """,
            (operation_name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def upsert_query(
        self,
        operation_name: str,
        query_id: str | None,
        decoration_id: str | None,
        source_asset: str | None,
        *,
        mark_success: bool = False,
    ) -> None:
        db = self._require()
        now = _iso(_utc_now())
        last_success = now if mark_success else None
        await db.execute(
            """
            INSERT INTO query_registry (
                operation_name, query_id, decoration_id, discovered_at, source_asset, last_success_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(operation_name) DO UPDATE SET
                query_id = COALESCE(excluded.query_id, query_registry.query_id),
                decoration_id = COALESCE(excluded.decoration_id, query_registry.decoration_id),
                discovered_at = excluded.discovered_at,
                source_asset = COALESCE(excluded.source_asset, query_registry.source_asset),
                last_success_at = COALESCE(excluded.last_success_at, query_registry.last_success_at)
            """,
            (operation_name, query_id, decoration_id, now, source_asset, last_success),
        )
        await db.commit()

    async def invalidate_query(self, operation_name: str) -> None:
        db = self._require()
        await db.execute("DELETE FROM query_registry WHERE operation_name = ?", (operation_name,))
        await db.commit()

    async def list_queries(self) -> list[dict[str, Any]]:
        db = self._require()
        cursor = await db.execute(
            "SELECT operation_name, query_id, decoration_id, discovered_at, source_asset, last_success_at FROM query_registry"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def set_session_outcome(self, slot: str, outcome: str) -> None:
        db = self._require()
        await db.execute(
            """
            INSERT INTO session_state (slot, last_outcome, last_outcome_at)
            VALUES (?, ?, ?)
            ON CONFLICT(slot) DO UPDATE SET
                last_outcome = excluded.last_outcome,
                last_outcome_at = excluded.last_outcome_at
            """,
            (slot, outcome, _iso(_utc_now())),
        )
        await db.commit()

    async def get_session_state(self, slot: str = "primary") -> dict[str, Any] | None:
        db = self._require()
        cursor = await db.execute(
            "SELECT slot, last_outcome, last_outcome_at FROM session_state WHERE slot = ?",
            (slot,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
