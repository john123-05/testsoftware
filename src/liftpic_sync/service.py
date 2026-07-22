from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime

from .asset_sync import AssetSyncWorker
from .config import Settings
from .envfile import load_env_file, write_env_values
from .operational_monitor import read_operational_status
from .remote_config import config_to_env
from .ride_tracker import RideTracker
from .scanner import FolderScanner
from .state import StateStore
from .statusfiles import read_local_status
from .supabase_client import SupabaseIngestClient
from .uploader import UploadWorker


log = logging.getLogger(__name__)


class LiftpicService:
    def __init__(self, settings: Settings, env_path: str | None = None):
        self.settings = settings
        self.env_path = env_path
        self.settings.ensure_dirs()
        self.store = StateStore(settings.state_db)
        self._build_workers()
        self._last_heartbeat = 0.0
        self._last_asset_sync = 0.0
        self._last_config_refresh = 0.0

    def _build_workers(self) -> None:
        self.ride_tracker = RideTracker(self.settings, self.store)
        self.scanner = FolderScanner(self.settings, self.store)
        self.uploader = UploadWorker(self.settings, self.store)
        self.asset_sync = AssetSyncWorker(self.settings, self.store)
        self.client = SupabaseIngestClient(self.settings)

    def close(self) -> None:
        self.store.close()

    def run_forever(self) -> None:
        log.info("starting %s for park=%s machine=%s shadow=%s", self.settings.app_name, self.settings.park_slug, self.settings.machine_id, self.settings.shadow_mode)
        while True:
            self._refresh_config_if_due()
            self.run_once()
            time.sleep(self.settings.poll_seconds)

    def _refresh_config_if_due(self) -> None:
        """Pull the dashboard config and apply changes live (shadow mode, upload
        mode, folder paths, ...) so edits in the Staff Dashboard reach a running
        PC without re-running the installer or re-pairing."""
        if not self.env_path or self.settings.config_refresh_seconds <= 0:
            return
        if not self.settings.device_token:
            return
        now = time.time()
        if now - self._last_config_refresh < self.settings.config_refresh_seconds:
            return
        self._last_config_refresh = now

        try:
            response = self.client.fetch_config()
        except Exception as exc:
            log.warning("config refresh failed: %s", exc)
            return

        config = response.get("config")
        if not isinstance(config, dict):
            return
        device_token = str(response.get("device_token") or self.settings.device_token)
        desired = config_to_env(config, device_token)

        current = load_env_file(self.env_path)
        changed = {key: value for key, value in desired.items() if current.get(key) != value}
        if not changed:
            return

        log.info("applying dashboard config changes: %s", ", ".join(sorted(changed)))
        write_env_values(self.env_path, desired)
        new_settings = Settings.from_env_file(self.env_path)
        self._apply_settings(new_settings)

    def _apply_settings(self, new_settings: Settings) -> None:
        was_shadow = self.settings.shadow_mode
        self.settings = new_settings
        self.settings.ensure_dirs()
        self._build_workers()
        if was_shadow and not new_settings.shadow_mode:
            released = self.store.requeue_shadowed()
            if released:
                log.info("shadow mode turned off: re-queued %s held photos for upload", released)

    def run_once(self) -> dict[str, object]:
        ride_result = self.ride_tracker.scan_once()
        asset_result = self._asset_sync_if_due()
        result = self.scanner.scan_once()
        uploaded = self.uploader.upload_due()
        counts = self.store.counts()
        ride_counts = self.store.ride_counts()
        log.info(
            "rides seen=%s new=%s assets=%s queued=%s staged=%s unstable=%s unknown=%s uploaded=%s counts=%s ride_counts=%s",
            ride_result.seen,
            ride_result.new,
            asset_result,
            result.queued,
            result.staged,
            result.skipped_unstable,
            result.skipped_unknown,
            uploaded,
            counts,
            ride_counts,
        )
        self._heartbeat_if_due(counts)
        return {
            "rides_seen": ride_result.seen,
            "rides_new": ride_result.new,
            "asset_sync": asset_result,
            "queued": result.queued,
            "staged": result.staged,
            "skipped_unstable": result.skipped_unstable,
            "skipped_unknown": result.skipped_unknown,
            "uploaded": uploaded,
            "counts": counts,
            "ride_counts": ride_counts,
        }

    def health(self) -> dict[str, object]:
        usage = shutil.disk_usage(self.settings.app_dir.anchor or ".")
        local_status = read_local_status(self.settings.statistic_file, self.settings.print_count_file)
        operational_status = read_operational_status(self.settings)
        ride_rollups = self.store.ride_rollups(
            park_id=self.settings.park_id,
            park_slug=self.settings.park_slug,
            machine_id=self.settings.machine_id,
            default_camera_code=self.settings.camera_code,
            days=self.settings.ride_rollup_days,
        )
        today = datetime.now().date().isoformat()
        today_rollups = [item for item in ride_rollups if item.get("business_date") == today]
        photos_taken_today = sum(int(item.get("photos_taken_count") or 0) for item in today_rollups)
        photos_sold_today = sum(int(item.get("photos_sold_count") or 0) for item in today_rollups)
        return {
            "app_name": self.settings.app_name,
            "park_slug": self.settings.park_slug,
            "park_id": self.settings.park_id,
            "machine_id": self.settings.machine_id,
            "camera_code": self.settings.camera_code,
            "shadow_mode": self.settings.shadow_mode,
            "state_db": str(self.settings.state_db),
            "log_dir": str(self.settings.log_dir),
            "counts": self.store.counts(),
            "ride_counts": self.store.ride_counts(),
            "asset_sync_enabled": self.settings.asset_sync_enabled,
            "asset_counts": self.store.asset_counts(),
            "operational_devices": [device.__dict__ for device in operational_status.devices],
            "operational_events": operational_status.events,
            "coin_status": operational_status.coin_status,
            "terminal_status": operational_status.terminal_status,
            "printer_status": operational_status.printer_status,
            "ride_rollups": ride_rollups,
            "photos_taken_today": photos_taken_today,
            "photos_sold_today": photos_sold_today,
            "photo_conversion_today": round(photos_sold_today / photos_taken_today, 4) if photos_taken_today else None,
            "disk_free_mb": int(usage.free / 1024 / 1024),
            "camera_status": operational_status.camera_status,
            "paper_remaining": local_status.paper_remaining,
            "paper_status": operational_status.printer_status or local_status.paper_status,
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

        try:
            self.client.status(payload)
            if self.settings.shadow_mode:
                log.info("shadow heartbeat sent: %s", payload)
        except Exception as exc:
            log.warning("heartbeat failed: %s", exc)

    def _asset_sync_if_due(self) -> dict[str, int] | None:
        if not self.settings.asset_sync_enabled:
            return None
        now = time.time()
        if now - self._last_asset_sync < self.settings.asset_sync_seconds:
            return None
        self._last_asset_sync = now

        if self.settings.shadow_mode:
            log.info("asset sync is enabled while upload shadow mode is active")

        try:
            result = self.asset_sync.sync_once()
            return {
                "fetched": result.fetched,
                "applied": result.applied,
                "skipped": result.skipped,
                "failed": result.failed,
            }
        except Exception as exc:
            log.warning("asset sync failed: %s", exc)
            return {"fetched": 0, "applied": 0, "skipped": 0, "failed": 1}
