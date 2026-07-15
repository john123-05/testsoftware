from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 3


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
    event_key: str | None = None


@dataclass(frozen=True)
class RideEvent:
    event_key: str
    capture_id: str
    park_slug: str
    park_id: str
    machine_id: str
    camera_code: str
    business_date: str
    captured_at: str
    source: str
    raw_path: str | None
    processed_path: str | None
    speed_kmh: float | None
    speed_status: str


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
                event_key TEXT PRIMARY KEY,
                capture_id TEXT NOT NULL,
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
        columns = {
            row["name"]
            for row in cur.execute("PRAGMA table_info(photo_events)").fetchall()
        }
        if "event_key" not in columns:
            cur.execute("ALTER TABLE photo_events ADD COLUMN event_key TEXT")
            cur.execute(
                """
                UPDATE photo_events
                SET event_key = substr(captured_at, 1, 10) || '|unknown|' || capture_id
                WHERE event_key IS NULL
                """
            )
        photo_columns = cur.execute("PRAGMA table_info(photo_events)").fetchall()
        capture_id_is_primary = any(row["name"] == "capture_id" and row["pk"] for row in photo_columns)
        if capture_id_is_primary:
            cur.execute("ALTER TABLE photo_events RENAME TO photo_events_capture_pk_backup")
            cur.execute(
                """
                CREATE TABLE photo_events (
                    event_key TEXT PRIMARY KEY,
                    capture_id TEXT NOT NULL,
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
                INSERT OR IGNORE INTO photo_events (
                    event_key, capture_id, raw_path, processed_path, legacy_filename,
                    captured_at, speed_kmh, speed_status, upload_status, checksum,
                    storage_path, raw_storage_path, retry_after, attempts, error,
                    metadata_json, created_at, updated_at
                )
                SELECT
                    COALESCE(event_key, substr(captured_at, 1, 10) || '|unknown|' || capture_id),
                    capture_id, raw_path, processed_path, legacy_filename,
                    captured_at, speed_kmh, speed_status, upload_status, checksum,
                    storage_path, raw_storage_path, retry_after, attempts, error,
                    metadata_json, created_at, updated_at
                FROM photo_events_capture_pk_backup
                """
            )
            cur.execute("DROP TABLE photo_events_capture_pk_backup")
        else:
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS photo_events_event_key_idx ON photo_events(event_key)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ride_events (
                event_key TEXT PRIMARY KEY,
                capture_id TEXT NOT NULL,
                park_slug TEXT NOT NULL,
                park_id TEXT,
                machine_id TEXT NOT NULL,
                camera_code TEXT NOT NULL,
                business_date TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                source TEXT NOT NULL,
                raw_path TEXT,
                processed_path TEXT,
                speed_kmh REAL,
                speed_status TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS ride_events_daily_idx
            ON ride_events(park_id, machine_id, camera_code, business_date)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS asset_deployments (
                deployment_id TEXT PRIMARY KEY,
                slot TEXT,
                target_path TEXT NOT NULL,
                source_bucket TEXT,
                source_path TEXT,
                sha256 TEXT,
                source_updated_at TEXT,
                applied_at REAL NOT NULL,
                backup_path TEXT,
                status TEXT NOT NULL,
                error TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS asset_deployments_status_idx
            ON asset_deployments(status, applied_at)
            """
        )
        if cur.execute("SELECT COUNT(*) FROM schema_state").fetchone()[0] == 0:
            cur.execute("INSERT INTO schema_state(version) VALUES (?)", (SCHEMA_VERSION,))
        else:
            cur.execute("UPDATE schema_state SET version=?", (SCHEMA_VERSION,))
        self.conn.commit()

    def upsert_event(self, event: PhotoEvent, metadata: dict[str, Any]) -> None:
        now = time.time()
        payload = json.dumps(metadata, sort_keys=True)
        event_key = event.event_key or f"{event.captured_at[:10]}|unknown|{event.capture_id}"
        self.conn.execute(
            """
            INSERT INTO photo_events (
                event_key, capture_id, raw_path, processed_path, legacy_filename, captured_at,
                speed_kmh, speed_status, upload_status, checksum, error,
                metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_key) DO UPDATE SET
                capture_id=excluded.capture_id,
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
                event_key,
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

    def upsert_ride_event(self, event: RideEvent) -> bool:
        exists = self.conn.execute(
            "SELECT 1 FROM ride_events WHERE event_key=?",
            (event.event_key,),
        ).fetchone()
        now = time.time()
        self.conn.execute(
            """
            INSERT INTO ride_events (
                event_key, capture_id, park_slug, park_id, machine_id, camera_code,
                business_date, captured_at, source, raw_path, processed_path,
                speed_kmh, speed_status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_key) DO UPDATE SET
                park_slug=excluded.park_slug,
                park_id=excluded.park_id,
                source=excluded.source,
                raw_path=COALESCE(excluded.raw_path, ride_events.raw_path),
                processed_path=COALESCE(excluded.processed_path, ride_events.processed_path),
                speed_kmh=COALESCE(excluded.speed_kmh, ride_events.speed_kmh),
                speed_status=CASE
                    WHEN excluded.speed_status = 'ok' THEN excluded.speed_status
                    ELSE ride_events.speed_status
                END,
                updated_at=excluded.updated_at
            """,
            (
                event.event_key,
                event.capture_id,
                event.park_slug,
                event.park_id,
                event.machine_id,
                event.camera_code,
                event.business_date,
                event.captured_at,
                event.source,
                event.raw_path,
                event.processed_path,
                event.speed_kmh,
                event.speed_status,
                now,
                now,
            ),
        )
        self.conn.commit()
        return exists is None

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

    def mark_uploaded(self, event_key: str, storage_path: str, raw_storage_path: str | None = None) -> None:
        self.conn.execute(
            """
            UPDATE photo_events
            SET upload_status='uploaded',
                storage_path=?,
                raw_storage_path=?,
                error=NULL,
                updated_at=?
            WHERE event_key=?
            """,
            (storage_path, raw_storage_path, time.time(), event_key),
        )
        self.conn.commit()

    def mark_shadowed(self, event_key: str, storage_path: str) -> None:
        self.conn.execute(
            """
            UPDATE photo_events
            SET upload_status='shadowed',
                storage_path=?,
                error=NULL,
                updated_at=?
            WHERE event_key=?
            """,
            (storage_path, time.time(), event_key),
        )
        self.conn.commit()

    def mark_retry(self, event_key: str, error: str, retry_after: float) -> None:
        self.conn.execute(
            """
            UPDATE photo_events
            SET upload_status='retry',
                attempts=attempts + 1,
                error=?,
                retry_after=?,
                updated_at=?
            WHERE event_key=?
            """,
            (error[:2000], retry_after, time.time(), event_key),
        )
        self.conn.commit()

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT upload_status, COUNT(*) AS count FROM photo_events GROUP BY upload_status"
        ).fetchall()
        return {row["upload_status"]: int(row["count"]) for row in rows}

    def ride_rollups(
        self,
        *,
        park_id: str,
        park_slug: str,
        machine_id: str,
        default_camera_code: str,
        days: int = 14,
    ) -> list[dict[str, Any]]:
        cutoff = (datetime.now() - timedelta(days=max(days - 1, 0))).date().isoformat()
        ride_rows = self.conn.execute(
            """
            SELECT
                business_date,
                camera_code,
                COUNT(*) AS photos_taken_count,
                MIN(captured_at) AS first_capture_at,
                MAX(captured_at) AS last_capture_at,
                SUM(CASE WHEN speed_status = 'ok' THEN 1 ELSE 0 END) AS speed_ok_count
            FROM ride_events
            WHERE business_date >= ?
            GROUP BY business_date, camera_code
            ORDER BY business_date DESC, camera_code ASC
            """,
            (cutoff,),
        ).fetchall()
        sold_rows = self.conn.execute(
            """
            SELECT
                substr(captured_at, 1, 10) AS business_date,
                COUNT(DISTINCT capture_id) AS photos_sold_count,
                MAX(captured_at) AS last_sale_at
            FROM photo_events
            WHERE substr(captured_at, 1, 10) >= ?
            GROUP BY substr(captured_at, 1, 10)
            """,
            (cutoff,),
        ).fetchall()
        sold_by_day = {
            (row["business_date"], default_camera_code): {
                "photos_sold_count": int(row["photos_sold_count"] or 0),
                "last_sale_at": row["last_sale_at"],
            }
            for row in sold_rows
            if row["business_date"]
        }

        rollups: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        for row in ride_rows:
            key = (row["business_date"], row["camera_code"])
            seen_keys.add(key)
            sold = sold_by_day.get(key, {"photos_sold_count": 0, "last_sale_at": None})
            taken = int(row["photos_taken_count"] or 0)
            sold_count = int(sold["photos_sold_count"] or 0)
            rollups.append(
                {
                    "park_id": park_id,
                    "park_slug": park_slug,
                    "machine_id": machine_id,
                    "camera_code": row["camera_code"],
                    "business_date": row["business_date"],
                    "photos_taken_count": taken,
                    "photos_sold_count": sold_count,
                    "conversion_rate": round(sold_count / taken, 4) if taken else None,
                    "first_capture_at": row["first_capture_at"],
                    "last_capture_at": row["last_capture_at"],
                    "last_sale_at": sold["last_sale_at"],
                    "speed_ok_count": int(row["speed_ok_count"] or 0),
                }
            )

        for key, sold in sold_by_day.items():
            if key in seen_keys:
                continue
            business_date, camera_code = key
            rollups.append(
                {
                    "park_id": park_id,
                    "park_slug": park_slug,
                    "machine_id": machine_id,
                    "camera_code": camera_code,
                    "business_date": business_date,
                    "photos_taken_count": 0,
                    "photos_sold_count": int(sold["photos_sold_count"] or 0),
                    "conversion_rate": None,
                    "first_capture_at": None,
                    "last_capture_at": None,
                    "last_sale_at": sold["last_sale_at"],
                    "speed_ok_count": 0,
                }
            )

        return sorted(rollups, key=lambda item: (str(item["business_date"]), str(item["camera_code"])), reverse=True)

    def ride_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT business_date, COUNT(*) AS count FROM ride_events GROUP BY business_date"
        ).fetchall()
        return {row["business_date"]: int(row["count"]) for row in rows}

    def asset_is_current(
        self,
        *,
        deployment_id: str,
        target_path: str,
        sha256: str | None,
        source_updated_at: str | None,
    ) -> bool:
        row = self.conn.execute(
            """
            SELECT target_path, sha256, source_updated_at, status
            FROM asset_deployments
            WHERE deployment_id=?
            """,
            (deployment_id,),
        ).fetchone()
        if not row or row["status"] != "applied" or row["target_path"] != target_path:
            return False
        if sha256:
            return row["sha256"] == sha256
        if source_updated_at:
            return row["source_updated_at"] == source_updated_at
        return True

    def record_asset_deployment(
        self,
        *,
        deployment_id: str,
        slot: str | None,
        target_path: str,
        source_bucket: str | None,
        source_path: str | None,
        sha256: str | None,
        source_updated_at: str | None,
        backup_path: str | None,
        status: str,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO asset_deployments (
                deployment_id, slot, target_path, source_bucket, source_path,
                sha256, source_updated_at, applied_at, backup_path, status, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(deployment_id) DO UPDATE SET
                slot=excluded.slot,
                target_path=excluded.target_path,
                source_bucket=excluded.source_bucket,
                source_path=excluded.source_path,
                sha256=excluded.sha256,
                source_updated_at=excluded.source_updated_at,
                applied_at=excluded.applied_at,
                backup_path=excluded.backup_path,
                status=excluded.status,
                error=excluded.error
            """,
            (
                deployment_id,
                slot,
                target_path,
                source_bucket,
                source_path,
                sha256,
                source_updated_at,
                time.time(),
                backup_path,
                status,
                error[:2000] if error else None,
            ),
        )
        self.conn.commit()

    def asset_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS count FROM asset_deployments GROUP BY status"
        ).fetchall()
        return {row["status"]: int(row["count"]) for row in rows}
