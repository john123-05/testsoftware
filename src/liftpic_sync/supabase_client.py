from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import Settings


class SupabaseIngestClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def begin(self, metadata: dict[str, Any], file_size: int) -> dict[str, Any]:
        return self._post_json(
            "liftpic-ingest-begin",
            {
                "metadata": metadata,
                "file_size": file_size,
            },
        )

    def commit(
        self,
        capture_id: str,
        storage_path: str,
        raw_storage_path: str | None = None,
        event_key: str | None = None,
    ) -> dict[str, Any]:
        return self._post_json(
            "liftpic-ingest-commit",
            {
                "capture_id": capture_id,
                "event_key": event_key,
                "storage_path": storage_path,
                "raw_storage_path": raw_storage_path,
            },
        )

    def status(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("liftpic-status", payload)

    def upload_signed(
        self,
        *,
        bucket: str | None,
        storage_path: str | None,
        token: str | None,
        signed_url: str | None,
        path: Path,
    ) -> None:
        if bucket and storage_path and token and self.settings.supabase_url and self.settings.supabase_anon_key:
            try:
                from supabase import create_client

                client = create_client(self.settings.supabase_url, self.settings.supabase_anon_key)
                with path.open("rb") as handle:
                    client.storage.from_(bucket).upload_to_signed_url(
                        path=storage_path,
                        token=token,
                        file=handle,
                    )
                return
            except ImportError:
                pass

        if not signed_url:
            raise RuntimeError("no signed_url available and official Supabase upload path is not configured")

        content_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        data = path.read_bytes()
        request = urllib.request.Request(
            signed_url,
            data=data,
            method="PUT",
            headers={
                "Content-Type": content_type,
                "Content-Length": str(len(data)),
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status >= 400:
                raise RuntimeError(f"signed upload failed with HTTP {response.status}")

    def _post_json(self, function_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.supabase_functions_url:
            raise RuntimeError("SUPABASE_FUNCTIONS_URL is not configured")
        if not self.settings.device_token:
            raise RuntimeError("DEVICE_TOKEN is not configured")

        url = f"{self.settings.supabase_functions_url}/{function_name}"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.device_token}",
                "X-Machine-ID": self.settings.machine_id,
                "X-Park-ID": self.settings.park_id,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{function_name} HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{function_name} network error: {exc}") from exc


def next_retry_after(delay_seconds: float, attempts: int) -> float:
    return time.time() + min(delay_seconds * max(1, attempts + 1), 300)
