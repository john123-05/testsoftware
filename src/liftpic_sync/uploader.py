from __future__ import annotations

import json
from pathlib import Path

from .config import Settings
from .state import StateStore
from .supabase_client import SupabaseIngestClient, next_retry_after


class UploadWorker:
    def __init__(self, settings: Settings, store: StateStore):
        self.settings = settings
        self.store = store
        self.client = SupabaseIngestClient(settings)

    def upload_due(self, limit: int = 10) -> int:
        uploaded = 0
        for row in self.store.due_uploads(limit):
            capture_id = row["capture_id"]
            try:
                source_path = self._source_path(row)
                metadata = json.loads(row["metadata_json"])

                if self.settings.shadow_mode:
                    storage_path = self._storage_path(row["legacy_filename"], row["captured_at"])
                    self.store.mark_shadowed(capture_id, f"shadow://{storage_path}")
                    uploaded += 1
                    continue

                begin = self.client.begin(metadata, source_path.stat().st_size)
                upload = begin.get("upload") or {}
                signed_url = upload.get("signed_url")
                token = upload.get("token")
                bucket = upload.get("bucket")
                storage_path = upload.get("storage_path")
                if not storage_path:
                    raise RuntimeError("begin did not return upload.storage_path")

                self.client.upload_signed(
                    bucket=bucket,
                    storage_path=storage_path,
                    token=token,
                    signed_url=signed_url,
                    path=source_path,
                )
                self.client.commit(capture_id, storage_path)
                self.store.mark_uploaded(capture_id, storage_path)
                uploaded += 1
            except Exception as exc:
                attempts = int(row["attempts"] or 0)
                self.store.mark_retry(
                    capture_id,
                    str(exc),
                    next_retry_after(self.settings.upload_retry_seconds, attempts),
                )
        return uploaded

    def _source_path(self, row) -> Path:
        processed = row["processed_path"]
        raw = row["raw_path"]
        source = processed or raw
        if not source:
            raise RuntimeError("event has no source path")
        path = Path(source)
        if not path.exists():
            raise RuntimeError(f"source file no longer exists: {path}")
        return path

    def _storage_path(self, legacy_filename: str, captured_at: str) -> str:
        date = captured_at[:10] if captured_at else "unknown-date"
        return f"processed/{self.settings.park_slug}/{date}/{legacy_filename}"
