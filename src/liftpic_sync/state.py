from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PhotoEvent:
    capture_id: str
    raw_path: str | None
    processed_path: str | None
    legacy_filename: str
    captured_at: str
    speed_kmh: float | None
    speed_status: str
    upload_status: str
    checksum: str | None = None
    error: str | None = None


class StateStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.migrate()

    def close(self) -> None:
        self.conn.close()

    def migrate(self) -> None:
        cur = self.conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_state (
                version INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS photo_events (
                capture_id TEXT PRIMARY KEY,
                raw_path TEXT,
                processed_path TEXT,
                legacy_filename TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                speed_kmh REAL,
                speed_status TEXT NOT NULL,
                upload_status TEXT NOT NULL,
                checksum TEXT,
                storage_path TEXT,
                raw_storage_path TEXT,
                retry_after REAL DEFAULT 0,
                attempts INTEGER DEFAULT 0,
                error TEXT,
                metadata_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        if cur.execute("SELECT COUNT(*) FROM schema_state").fetchone()[0] == 0:
            cur.execute("INSERT INTO schema_state(version) VALUES (?)", (SCHEMA_VERSION,))
        self.conn.commit()

    def upsert_event(self, event: PhotoEvent, metadata: dict[str, Any]) -> None:
        now = time.time()
        payload = json.dumps(metadata, sort_keys=True)
        self.conn.execute(
            """
            INSERT INTO photo_events (
                capture_id, raw_path, processed_path, legacy_filename, captured_at,
                speed_kmh, speed_status, upload_status, checksum, error,
                metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(capture_id) DO UPDATE SET
                raw_path=COALESCE(excluded.raw_path, photo_events.raw_path),
                processed_path=COALESCE(excluded.processed_path, photo_events.processed_path),
                legacy_filename=excluded.legacy_filename,
                captured_at=excluded.captured_at,
                speed_kmh=excluded.speed_kmh,
                speed_status=excluded.speed_status,
                checksum=COALESCE(excluded.checksum, photo_events.checksum),
                error=excluded.error,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                event.capture_id,
                event.raw_path,
                event.processed_path,
                event.legacy_filename,
                event.captured_at,
                event.speed_kmh,
                event.speed_status,
                event.upload_status,
                event.checksum,
                event.error,
                payload,
                now,
                now,
            ),
        )
        self.conn.commit()

    def due_uploads(self, limit: int = 20) -> Iterable[sqlite3.Row]:
        now = time.time()
        return self.conn.execute(
            """
            SELECT * FROM photo_events
            WHERE upload_status IN ('queued', 'retry')
              AND retry_after <= ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (now, limit),
        ).fetchall()

    def mark_uploaded(self, capture_id: str, storage_path: str, raw_storage_path: str | None = None) -> None:
        self.conn.execute(
            """
            UPDATE photo_events
            SET upload_status='uploaded',
                storage_path=?,
                raw_storage_path=?,
                error=NULL,
                updated_at=?
            WHERE capture_id=?
            """,
            (storage_path, raw_storage_path, time.time(), capture_id),
        )
        self.conn.commit()

    def mark_shadowed(self, capture_id: str, storage_path: str) -> None:
        self.conn.execute(
            """
            UPDATE photo_events
            SET upload_status='shadowed',
                storage_path=?,
                error=NULL,
                updated_at=?
            WHERE capture_id=?
            """,
            (storage_path, time.time(), capture_id),
        )
        self.conn.commit()

    def mark_retry(self, capture_id: str, error: str, retry_after: float) -> None:
        self.conn.execute(
            """
            UPDATE photo_events
            SET upload_status='retry',
                attempts=attempts + 1,
                error=?,
                retry_after=?,
                updated_at=?
            WHERE capture_id=?
            """,
            (error[:2000], retry_after, time.time(), capture_id),
        )
        self.conn.commit()

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT upload_status, COUNT(*) AS count FROM photo_events GROUP BY upload_status"
        ).fetchall()
        return {row["upload_status"]: int(row["count"]) for row in rows}
