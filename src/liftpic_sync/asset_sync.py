from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .files import sha256_file
from .state import StateStore
from .supabase_client import SupabaseIngestClient


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssetSyncResult:
    fetched: int = 0
    applied: int = 0
    skipped: int = 0
    failed: int = 0


class AssetSyncWorker:
    """Download dashboard-managed local UI/print assets onto this PC."""

    def __init__(
        self,
        settings: Settings,
        store: StateStore,
        client: SupabaseIngestClient | None = None,
    ):
        self.settings = settings
        self.store = store
        self.client = client or SupabaseIngestClient(settings)
        self.allowed_roots = tuple(settings.asset_allowed_roots)

    def sync_once(self) -> AssetSyncResult:
        response = self.client.assets()
        assets = response.get("assets") or []
        if not isinstance(assets, list):
            raise RuntimeError("liftpic-assets did not return an assets list")

        result = AssetSyncResult(fetched=len(assets))
        applied = skipped = failed = 0
        for asset in assets:
            if not isinstance(asset, dict):
                failed += 1
                continue
            try:
                outcome = self._sync_asset(asset)
                if outcome == "applied":
                    applied += 1
                else:
                    skipped += 1
            except Exception as exc:
                failed += 1
                self._record_failure(asset, str(exc))
                log.warning("asset sync failed: %s", exc)

        return AssetSyncResult(
            fetched=result.fetched,
            applied=applied,
            skipped=skipped,
            failed=failed,
        )

    def _sync_asset(self, asset: dict[str, Any]) -> str:
        deployment_id = self._deployment_id(asset)
        slot = self._optional_str(asset.get("slot"))
        target_path_raw = self._required_str(asset.get("target_path"), "target_path")
        target = self._allowed_target(target_path_raw)
        sha256 = self._optional_str(asset.get("sha256"))
        source_updated_at = self._optional_str(asset.get("updated_at"))
        bucket = self._optional_str(asset.get("bucket"))
        storage_path = self._optional_str(asset.get("storage_path"))

        if self.store.asset_is_current(
            deployment_id=deployment_id,
            target_path=str(target),
            sha256=sha256,
            source_updated_at=source_updated_at,
        ):
            return "skipped"

        if sha256 and target.exists() and sha256_file(target).lower() == sha256.lower():
            self._record_applied(asset, target, backup_path=None)
            return "skipped"

        signed_url = self._required_str(asset.get("signed_url"), "signed_url")
        data = self.client.download_signed_url(signed_url)
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if sha256 and actual_sha256.lower() != sha256.lower():
            raise RuntimeError(
                f"downloaded asset hash mismatch for {target}: expected {sha256}, got {actual_sha256}"
            )

        backup_path = self._backup_existing(target, deployment_id)
        self._atomic_write(target, data)
        self.store.record_asset_deployment(
            deployment_id=deployment_id,
            slot=slot,
            target_path=str(target),
            source_bucket=bucket,
            source_path=storage_path,
            sha256=sha256 or actual_sha256,
            source_updated_at=source_updated_at,
            backup_path=str(backup_path) if backup_path else None,
            status="applied",
            error=None,
        )
        return "applied"

    def _record_applied(self, asset: dict[str, Any], target: Path, backup_path: Path | None) -> None:
        self.store.record_asset_deployment(
            deployment_id=self._deployment_id(asset),
            slot=self._optional_str(asset.get("slot")),
            target_path=str(target),
            source_bucket=self._optional_str(asset.get("bucket")),
            source_path=self._optional_str(asset.get("storage_path")),
            sha256=self._optional_str(asset.get("sha256")),
            source_updated_at=self._optional_str(asset.get("updated_at")),
            backup_path=str(backup_path) if backup_path else None,
            status="applied",
            error=None,
        )

    def _record_failure(self, asset: dict[str, Any], error: str) -> None:
        target_path = str(asset.get("target_path") or "<missing>")
        self.store.record_asset_deployment(
            deployment_id=self._deployment_id(asset),
            slot=self._optional_str(asset.get("slot")),
            target_path=target_path,
            source_bucket=self._optional_str(asset.get("bucket")),
            source_path=self._optional_str(asset.get("storage_path")),
            sha256=self._optional_str(asset.get("sha256")),
            source_updated_at=self._optional_str(asset.get("updated_at")),
            backup_path=None,
            status="failed",
            error=error,
        )

    def _allowed_target(self, raw_path: str) -> Path:
        if not self.allowed_roots:
            raise RuntimeError("ASSET_SYNC_ALLOWED_ROOTS is empty")
        target = Path(raw_path).expanduser().resolve(strict=False)
        target_norm = self._norm(target)
        for root in self.allowed_roots:
            root_norm = self._norm(Path(root).expanduser().resolve(strict=False))
            try:
                if os.path.commonpath([target_norm, root_norm]) == root_norm:
                    return target
            except ValueError:
                continue
        raise RuntimeError(f"asset target is outside allowed roots: {raw_path}")

    def _backup_existing(self, target: Path, deployment_id: str) -> Path | None:
        if not target.exists():
            return None
        backup_root = self.settings.asset_backup_dir
        if backup_root is None:
            return None
        relative = self._relative_to_allowed_root(target)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_root / timestamp / deployment_id[:8] / relative
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(target.read_bytes())
        return backup_path

    def _relative_to_allowed_root(self, target: Path) -> Path:
        target_resolved = target.resolve(strict=False)
        for root in self.allowed_roots:
            root_resolved = Path(root).expanduser().resolve(strict=False)
            try:
                return target_resolved.relative_to(root_resolved)
            except ValueError:
                continue
        safe_parts = [part.replace(":", "").replace("\\", "_").replace("/", "_") for part in target.parts if part]
        return Path(*safe_parts)

    @staticmethod
    def _atomic_write(target: Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f"{target.name}.liftpic-sync.tmp")
        temp.write_bytes(data)
        temp.replace(target)

    @staticmethod
    def _deployment_id(asset: dict[str, Any]) -> str:
        raw = str(asset.get("id") or "").strip()
        if raw:
            return raw
        target = str(asset.get("target_path") or "")
        sha256 = str(asset.get("sha256") or "")
        updated_at = str(asset.get("updated_at") or "")
        digest = hashlib.sha256(f"{target}|{sha256}|{updated_at}".encode("utf-8")).hexdigest()
        return digest

    @staticmethod
    def _required_str(value: object, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"asset is missing {name}")
        return value.strip()

    @staticmethod
    def _optional_str(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    @staticmethod
    def _norm(path: Path) -> str:
        return os.path.normcase(os.path.abspath(str(path)))
