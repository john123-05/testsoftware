from __future__ import annotations

import logging
import shutil
import time

from .config import Settings
from .scanner import FolderScanner
from .state import StateStore
from .statusfiles import read_local_status
from .supabase_client import SupabaseIngestClient
from .uploader import UploadWorker


log = logging.getLogger(__name__)


class LiftpicService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.ensure_dirs()
        self.store = StateStore(settings.state_db)
        self.scanner = FolderScanner(settings, self.store)
        self.uploader = UploadWorker(settings, self.store)
        self.client = SupabaseIngestClient(settings)
        self._last_heartbeat = 0.0

    def close(self) -> None:
        self.store.close()

    def run_forever(self) -> None:
        log.info("starting %s for park=%s machine=%s shadow=%s", self.settings.app_name, self.settings.park_slug, self.settings.machine_id, self.settings.shadow_mode)
        while True:
            self.run_once()
            time.sleep(self.settings.poll_seconds)

    def run_once(self) -> dict[str, object]:
        result = self.scanner.scan_once()
        uploaded = self.uploader.upload_due()
        counts = self.store.counts()
        log.info(
            "scan queued=%s staged=%s unstable=%s unknown=%s uploaded=%s counts=%s",
            result.queued,
            result.staged,
            result.skipped_unstable,
            result.skipped_unknown,
            uploaded,
            counts,
        )
        self._heartbeat_if_due(counts)
        return {
            "queued": result.queued,
            "staged": result.staged,
            "skipped_unstable": result.skipped_unstable,
            "skipped_unknown": result.skipped_unknown,
            "uploaded": uploaded,
            "counts": counts,
        }

    def health(self) -> dict[str, object]:
        usage = shutil.disk_usage(self.settings.app_dir.anchor or ".")
        local_status = read_local_status(self.settings.statistic_file, self.settings.print_count_file)
        return {
            "app_name": self.settings.app_name,
            "park_slug": self.settings.park_slug,
            "park_id": self.settings.park_id,
            "machine_id": self.settings.machine_id,
            "shadow_mode": self.settings.shadow_mode,
            "state_db": str(self.settings.state_db),
            "log_dir": str(self.settings.log_dir),
            "counts": self.store.counts(),
            "disk_free_mb": int(usage.free / 1024 / 1024),
            "paper_remaining": local_status.paper_remaining,
            "paper_status": local_status.paper_status,
            "statistic_file_size": local_status.statistic_file_size,
            "statistic_last_line": local_status.statistic_last_line,
        }

    def _heartbeat_if_due(self, counts: dict[str, int]) -> None:
        now = time.time()
        if now - self._last_heartbeat < self.settings.heartbeat_seconds:
            return
        self._last_heartbeat = now
        payload = self.health()
        payload["queue_count"] = counts.get("queued", 0) + counts.get("retry", 0)

        if self.settings.shadow_mode:
            log.info("shadow heartbeat: %s", payload)
            return

        try:
            self.client.status(payload)
        except Exception as exc:
            log.warning("heartbeat failed: %s", exc)
