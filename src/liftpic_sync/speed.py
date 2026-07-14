from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .filename_codec import parse_capture_filename


SPEED_LOG_RE = re.compile(r"Measured speed:\s*(?P<speed>\d+(?:[,.]\d+)?)\s*km/h", re.I)
EVENT_RE = re.compile(r"Event started at\s+(?P<time>\d{2}:\d{2}:\d{2})", re.I)
NEWEST_FILE_RE = re.compile(r"Newest file is\s+(?P<file>\S+)", re.I)


@dataclass(frozen=True)
class SpeedMatch:
    speed_kmh: float | None
    status: str
    source: str
    delta_seconds: float | None = None


def speed_from_processed_name(filename: str) -> SpeedMatch:
    parsed = parse_capture_filename(filename)
    if parsed and parsed.speed_kmh is not None:
        return SpeedMatch(parsed.speed_kmh, "ok", "processed_filename", 0.0)
    return SpeedMatch(None, "missing", "processed_filename", None)


def find_matching_processed_file(
    processed_dir: Path,
    capture_id: str,
    raw_mtime: float | None,
    max_delta_seconds: float,
) -> tuple[Path | None, SpeedMatch]:
    if not processed_dir.exists():
        return None, SpeedMatch(None, "missing", "processed_dir_missing", None)

    candidates: list[tuple[Path, float | None, SpeedMatch]] = []
    for path in processed_dir.glob("*.jp*g"):
        parsed = parse_capture_filename(path.name)
        if not parsed or parsed.capture_id != capture_id:
            continue
        delta = None
        if raw_mtime is not None:
            delta = abs(path.stat().st_mtime - raw_mtime)
        candidates.append((path, delta, speed_from_processed_name(path.name)))

    if not candidates:
        return None, SpeedMatch(None, "missing", "processed_dir", None)

    if raw_mtime is None:
        path, delta, match = sorted(candidates, key=lambda item: item[0].stat().st_mtime)[-1]
        return path, match

    candidates.sort(key=lambda item: item[1] if item[1] is not None else 999999.0)
    best_path, best_delta, best_match = candidates[0]
    if best_delta is not None and best_delta > max_delta_seconds:
        return best_path, SpeedMatch(best_match.speed_kmh, "ambiguous", best_match.source, best_delta)
    return best_path, SpeedMatch(best_match.speed_kmh, best_match.status, best_match.source, best_delta)


def parse_aidatest_log_tail(lines: list[str]) -> list[SpeedMatch]:
    matches: list[SpeedMatch] = []
    current_speed: float | None = None
    for line in lines:
        speed_match = SPEED_LOG_RE.search(line)
        if speed_match:
            raw = speed_match.group("speed").replace(",", ".")
            current_speed = float(raw)
            continue
        newest = NEWEST_FILE_RE.search(line)
        if newest and current_speed is not None:
            matches.append(SpeedMatch(current_speed, "ok", "aidatest_log", None))
            current_speed = None
    return matches


def timestamp_from_path(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)
