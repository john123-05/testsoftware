from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .filename_codec import build_legacy_filename, parse_capture_filename
from .files import is_image, is_stable, sha256_file
from .identity import build_event_key
from .speed import find_matching_processed_file, speed_from_processed_name
from .state import PhotoEvent, StateStore


@dataclass(frozen=True)
class ScanResult:
    queued: int
    staged: int
    skipped_unstable: int
    skipped_unknown: int


class FolderScanner:
    def __init__(self, settings: Settings, store: StateStore):
        self.settings = settings
        self.store = store

    def scan_once(self) -> ScanResult:
        queued = 0
        staged = 0
        skipped_unstable = 0
        skipped_unknown = 0
        seen_capture_ids: set[str] = set()

        for path in self._candidate_images():
            if not is_stable(path, self.settings.file_stable_seconds):
                skipped_unstable += 1
                continue

            parsed = parse_capture_filename(path.name)
            if not parsed:
                skipped_unknown += 1
                continue
            if parsed.capture_id in seen_capture_ids:
                continue
            seen_capture_ids.add(parsed.capture_id)

            raw_path = path if path.parent == self.settings.raw_dir else None
            processed_path: Path | None = None
            speed_match = speed_from_processed_name(path.name)
            sold_source_path = path if self._is_qrcode_path(path) else None

            if path.parent == self.settings.processed_dir:
                processed_path = path
            else:
                processed_path, speed_match = find_matching_processed_file(
                    self.settings.processed_dir,
                    parsed.capture_id,
                    path.stat().st_mtime,
                    self.settings.speed_match_seconds,
                )

            reference_path = processed_path or raw_path or path
            reference_parsed = parse_capture_filename(reference_path.name)
            captured_at = parsed.timestamp or (reference_parsed.timestamp if reference_parsed else None) or datetime.fromtimestamp(
                reference_path.stat().st_mtime,
                tz=timezone.utc,
            )
            legacy = build_legacy_filename(
                customer_code=self.settings.customer_code,
                capture_id=parsed.capture_id,
                captured_at=captured_at,
            )
            business_date = captured_at.date().isoformat()
            event_key = build_event_key(
                machine_id=self.settings.machine_id,
                camera_code=self.settings.camera_code,
                business_date=business_date,
                capture_id=parsed.capture_id,
            )
            stage_path = self._stage_if_needed(path, legacy.filename)
            if stage_path != path:
                staged += 1
            source_path = stage_path or path
            checksum = sha256_file(source_path)
            status = "queued"
            metadata = {
                "park_slug": self.settings.park_slug,
                "park_id": self.settings.park_id,
                "machine_id": self.settings.machine_id,
                "camera_code": self.settings.camera_code,
                "event_key": event_key,
                "business_date": business_date,
                "capture_id": parsed.capture_id,
                "legacy_filename": legacy.filename,
                "legacy_code": legacy.legacy_code,
                "time_code": legacy.time_code,
                "file_code": legacy.file_code,
                "customer_code": self.settings.customer_code,
                "captured_at": captured_at.isoformat(),
                "raw_path": str(raw_path) if raw_path else None,
                "processed_path": str(source_path),
                "sold_source_path": str(sold_source_path) if sold_source_path else None,
                "webout_path": str(source_path) if self._is_webout_path(source_path) else None,
                "speed_kmh": speed_match.speed_kmh,
                "speed_status": speed_match.status,
                "speed_source": speed_match.source,
                "checksum_sha256": checksum,
            }
            event = PhotoEvent(
                capture_id=parsed.capture_id,
                raw_path=str(raw_path) if raw_path else None,
                processed_path=str(source_path),
                legacy_filename=legacy.filename,
                captured_at=captured_at.isoformat(),
                speed_kmh=speed_match.speed_kmh,
                speed_status=speed_match.status,
                upload_status=status,
                checksum=checksum,
                event_key=event_key,
            )
            self.store.upsert_event(event, metadata)
            queued += 1

        return ScanResult(queued, staged, skipped_unstable, skipped_unknown)

    def _candidate_images(self) -> list[Path]:
        candidates: list[Path] = []
        for folder in self._scan_folders():
            if folder.exists():
                candidates.extend(path for path in folder.iterdir() if is_image(path))
        return sorted(candidates, key=lambda path: path.stat().st_mtime)

    def _scan_folders(self) -> list[Path]:
        if self.settings.upload_source == "qrcode" and self.settings.qrcode_dir:
            folders = [self.settings.qrcode_dir]
        elif self.settings.upload_source == "webout" and self.settings.webout_dir:
            folders = [self.settings.webout_dir]
        else:
            folders = [self.settings.raw_dir, self.settings.processed_dir]
            if self.settings.webout_dir:
                folders.append(self.settings.webout_dir)
            if self.settings.qrcode_dir:
                folders.append(self.settings.qrcode_dir)

        unique: list[Path] = []
        seen: set[str] = set()
        for folder in folders:
            key = str(folder).lower()
            if key not in seen:
                seen.add(key)
                unique.append(folder)
        return unique

    def _stage_if_needed(self, source: Path, legacy_filename: str) -> Path:
        if not self._is_qrcode_path(source):
            return source
        if self.settings.shadow_mode and not self.settings.stage_in_shadow:
            return source
        if not self.settings.webout_dir:
            return source

        self.settings.webout_dir.mkdir(parents=True, exist_ok=True)
        target = self.settings.webout_dir / legacy_filename
        if not target.exists():
            shutil.copy2(source, target)
        return target

    def _is_qrcode_path(self, path: Path) -> bool:
        return bool(self.settings.qrcode_dir and path.parent.resolve() == self.settings.qrcode_dir.resolve())

    def _is_webout_path(self, path: Path) -> bool:
        return bool(self.settings.webout_dir and path.parent.resolve() == self.settings.webout_dir.resolve())
