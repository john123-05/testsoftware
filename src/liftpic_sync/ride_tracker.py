from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import Settings
from .filename_codec import parse_capture_filename
from .files import is_image, is_stable
from .identity import build_event_key
from .speed import find_matching_processed_file, speed_from_processed_name
from .state import RideEvent, StateStore


@dataclass(frozen=True)
class RideScanResult:
    seen: int
    new: int
    skipped_unstable: int
    skipped_unknown: int


class RideTracker:
    def __init__(self, settings: Settings, store: StateStore):
        self.settings = settings
        self.store = store

    def scan_once(self) -> RideScanResult:
        if not self.settings.ride_count_enabled:
            return RideScanResult(0, 0, 0, 0)

        seen = 0
        new = 0
        skipped_unstable = 0
        skipped_unknown = 0

        for path in self._candidate_images():
            if not is_stable(path, self.settings.file_stable_seconds):
                skipped_unstable += 1
                continue

            parsed = parse_capture_filename(path.name)
            if not parsed:
                skipped_unknown += 1
                continue

            raw_path: Path | None = path if self._same_folder(path.parent, self.settings.raw_dir) else None
            processed_path: Path | None = path if self._same_folder(path.parent, self.settings.processed_dir) else None
            speed_match = speed_from_processed_name(path.name)

            if not processed_path:
                processed_path, speed_match = find_matching_processed_file(
                    self.settings.processed_dir,
                    parsed.capture_id,
                    path.stat().st_mtime,
                    self.settings.speed_match_seconds,
                )

            processed_parsed = parse_capture_filename(processed_path.name) if processed_path else None
            captured_at = (
                parsed.timestamp
                or (processed_parsed.timestamp if processed_parsed else None)
                or self._local_mtime(processed_path or raw_path or path)
            )
            business_date = captured_at.date().isoformat()
            source = "processed" if processed_path and self._same_folder(path.parent, self.settings.processed_dir) else "raw"
            event_key = build_event_key(
                machine_id=self.settings.machine_id,
                camera_code=self.settings.camera_code,
                business_date=business_date,
                capture_id=parsed.capture_id,
            )
            event = RideEvent(
                event_key=event_key,
                capture_id=parsed.capture_id,
                park_slug=self.settings.park_slug,
                park_id=self.settings.park_id,
                machine_id=self.settings.machine_id,
                camera_code=self.settings.camera_code,
                business_date=business_date,
                captured_at=captured_at.isoformat(),
                source=source,
                raw_path=str(raw_path) if raw_path else None,
                processed_path=str(processed_path) if processed_path else None,
                speed_kmh=speed_match.speed_kmh,
                speed_status=speed_match.status,
            )
            seen += 1
            if self.store.upsert_ride_event(event):
                new += 1

        return RideScanResult(seen, new, skipped_unstable, skipped_unknown)

    def _candidate_images(self) -> list[Path]:
        candidates: list[Path] = []
        for folder in self._scan_folders():
            if folder.exists():
                candidates.extend(path for path in folder.iterdir() if is_image(path))
        return sorted(candidates, key=lambda path: path.stat().st_mtime)

    def _scan_folders(self) -> list[Path]:
        source = self.settings.ride_count_source.replace(";", ",")
        requested = {part.strip() for part in source.split(",") if part.strip()}
        if "all" in requested or "raw_and_processed" in requested:
            requested.update({"raw", "processed"})

        folders: list[Path] = []
        if "processed" in requested or not requested:
            folders.append(self.settings.processed_dir)
        if "raw" in requested:
            folders.append(self.settings.raw_dir)

        unique: list[Path] = []
        seen: set[str] = set()
        for folder in folders:
            key = str(folder.resolve()).lower()
            if key not in seen:
                seen.add(key)
                unique.append(folder)
        return unique

    @staticmethod
    def _local_mtime(path: Path) -> datetime:
        return datetime.fromtimestamp(path.stat().st_mtime)

    @staticmethod
    def _same_folder(left: Path, right: Path) -> bool:
        return str(left.resolve()).lower() == str(right.resolve()).lower()
