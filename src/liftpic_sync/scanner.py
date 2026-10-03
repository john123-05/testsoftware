from __future__ import annotations

import re
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

# A sold-photo line in a Statistic.txt-style sale log, e.g.:
#   03.10.2026 16:00:28::C:\liftpic\fotos\00302_202610031538093871.jpg::3
# Used by UPLOAD_SOURCE=statistic (Plose: the sale software has no qrcode
# staging step at all - pressing "Kaufen" only appends a line here).
STATISTIC_SOLD_LINE_RE = re.compile(r"::(?P<path>[A-Za-z]:\\[^:]+?\.jpe?g)::", re.I)


def _tail_text_lines(path: Path, max_bytes: int = 256_000) -> list[str]:
    """Last `max_bytes` of a text log, split into non-empty lines.

    Statistic.txt only grows (one line per sale) and is read on every scan
    cycle, so this avoids loading a file that could grow large over a long
    season into memory in full each time - mirrors operational_monitor's
    _tail_lines approach.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            raw = handle.read()
    except OSError:
        return []
    text = raw.decode("utf-8", errors="replace")
    if text.count("\ufffd") > 8:
        text = raw.decode("latin1", errors="replace")
    return [line for line in text.splitlines() if line.strip()]


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

            # Already uploaded on an earlier run/day? Skip. jpeg4web leaves sold
            # photos in qrcode and can re-touch them (new mtime), which would
            # otherwise re-queue them under a new, wrong date and create phantom
            # duplicate "sales" the next morning. Dedup is stable per capture_id.
            if self.store.has_uploaded_capture(parsed.capture_id):
                continue

            raw_path = path if path.parent == self.settings.raw_dir else None
            processed_path: Path | None = None
            speed_match = speed_from_processed_name(path.name)
            # The server only turns an upload into a claimable `photos` row
            # (with real speed/captured_at - see liftpic-ingest-commit's
            # writeClaimablePhoto) when sold_source_path is set. Normally that
            # means "sat in the qrcode folder". With upload_source=statistic
            # there is no qrcode folder at all - every candidate here already
            # IS a confirmed sale (it came straight from the sale log), so it
            # counts as sold too.
            sold_source_path = (
                path
                if self._is_qrcode_path(path) or self.settings.upload_source == "statistic"
                else None
            )

            if path.parent == self.settings.processed_dir:
                processed_path = path
            elif speed_match.status != "ok":
                # Only search processed_dir for a speed match when the file's
                # own name didn't already carry one - e.g. a qrcode-folder file
                # that still has the AidaTest speed suffix. Previously this ran
                # unconditionally and discarded an already-correct speed_match
                # from the line above whenever the file wasn't literally in
                # processed_dir, even if processed_dir had nothing to offer
                # (empty/already cleaned up), silently losing a known speed.
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
                file_code_positions=self.settings.file_code_positions,
            )
            business_date = captured_at.date().isoformat()
            event_key = build_event_key(
                machine_id=self.settings.machine_id,
                camera_code=self.settings.camera_code,
                business_date=business_date,
                capture_id=parsed.capture_id,
            )
            # Read-only: upload the purchased photo straight from where the
            # camera chain put it (qrcode), never copying/staging anything onto
            # the customer's system. The uploaded name is assigned by the server
            # from legacy_filename in the metadata, so no local rename is needed.
            source_path = path
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
        if self.settings.upload_source == "statistic":
            return self._statistic_sold_images()

        candidates: list[Path] = []
        for folder in self._scan_folders():
            if folder.exists():
                candidates.extend(path for path in folder.iterdir() if is_image(path))
        return sorted(candidates, key=lambda path: path.stat().st_mtime)

    def _statistic_sold_images(self) -> list[Path]:
        """Sold photos for sale software with no qrcode staging step.

        Instead of watching a folder for sold files, this reads which photos
        were actually sold from the sale log itself (settings.statistic_file)
        and resolves each one back to its real file on disk - preferring the
        processed copy (it may carry a speed suffix the raw capture doesn't).
        """
        stat_file = self.settings.statistic_file
        if not stat_file or not stat_file.exists():
            return []

        seen: set[str] = set()
        candidates: list[Path] = []
        for line in _tail_text_lines(stat_file):
            match = STATISTIC_SOLD_LINE_RE.search(line)
            if not match:
                continue
            # String split, not Path(...).name: the logged path is always
            # Windows-style (backslashes), but pathlib only treats backslash
            # as a separator on Windows itself - on any other OS (incl. this
            # test suite) Path(...).name would return the whole string.
            basename = match.group("path").strip().replace("/", "\\").rsplit("\\", 1)[-1]
            if basename in seen:
                continue
            seen.add(basename)
            resolved = self._resolve_sold_filename(basename)
            if resolved:
                candidates.append(resolved)
        return candidates

    def _resolve_sold_filename(self, basename: str) -> Path | None:
        parsed = parse_capture_filename(basename)
        if not parsed:
            return None

        processed_match, _ = find_matching_processed_file(
            self.settings.processed_dir, parsed.capture_id, None, self.settings.speed_match_seconds
        )
        if processed_match:
            return processed_match

        raw_candidate = self.settings.raw_dir / basename
        if raw_candidate.exists():
            return raw_candidate
        return None

    def _scan_folders(self) -> list[Path]:
        if self.settings.upload_source == "qrcode" and self.settings.qrcode_dir:
            folders = [self.settings.qrcode_dir]
            if self.settings.qrcode_dir_2:
                folders.append(self.settings.qrcode_dir_2)
        elif self.settings.upload_source == "webout" and self.settings.webout_dir:
            folders = [self.settings.webout_dir]
        else:
            folders = [self.settings.raw_dir, self.settings.processed_dir]
            if self.settings.webout_dir:
                folders.append(self.settings.webout_dir)
            if self.settings.qrcode_dir:
                folders.append(self.settings.qrcode_dir)
            if self.settings.qrcode_dir_2:
                folders.append(self.settings.qrcode_dir_2)

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
        resolved = path.parent.resolve()
        if self.settings.qrcode_dir and resolved == self.settings.qrcode_dir.resolve():
            return True
        return bool(self.settings.qrcode_dir_2 and resolved == self.settings.qrcode_dir_2.resolve())

    def _is_webout_path(self, path: Path) -> bool:
        return bool(self.settings.webout_dir and path.parent.resolve() == self.settings.webout_dir.resolve())
