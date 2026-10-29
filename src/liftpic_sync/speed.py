from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .filename_codec import parse_capture_filename


SPEED_LOG_RE = re.compile(r"Measured speed:\s*(?P<speed>\d+(?:[,.]\d+)?)\s*km/h", re.I)
EVENT_RE = re.compile(r"Event started at\s+(?P<time>\d{2}:\d{2}:\d{2})", re.I)
NEWEST_FILE_RE = re.compile(r"Newest file is\s+(?P<file>\S+)", re.I)
# Speedshot's [SpeedLog] file (Weissenfels: C:\liftpic\speedshot\test.txt), one line per ride:
#   00092.jpg;28.10.2026 16:55:00;7,81 m/s(=28,13 km/h);
# Used where Speedshot runs with SaveInfoToImageFilename=0, i.e. the speed is only painted
# into the photo and never reaches the file name.
SPEEDSHOT_LINE_RE = re.compile(
    r"^\s*[a-z]?(?P<capture>\d{1,8})\.jpe?g;(?P<day>\d{2}\.\d{2}\.\d{4})\s+\d{2}:\d{2}:\d{2};"
    r"[^;]*?\(=\s*(?P<kmh>\d+(?:[,.]\d+)?)\s*km/h",
    re.I,
)
# The log only ever grows (22 MB after a few seasons); the end holds every ride still waiting
# for an upload, so only that part is read - and only again once the file has changed.
SPEEDSHOT_TAIL_BYTES = 2_000_000
_speedshot_cache: dict[str, tuple[int, int, dict[tuple[str, date], float]]] = {}


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


def capture_time(path: Path) -> datetime:
    """When the photo was taken: the timestamp in its name, else its local mtime."""
    parsed = parse_capture_filename(path.name)
    if parsed and parsed.timestamp:
        return parsed.timestamp
    return datetime.fromtimestamp(path.stat().st_mtime)


def find_same_day_processed_file(
    processed_dir: Path,
    capture_id: str,
    reference_mtime: float,
    max_delta_seconds: float,
) -> tuple[Path | None, SpeedMatch]:
    """find_matching_processed_file for cameras whose counter restarts daily.

    There the processed folder can hold the same capture number from several
    days; only a copy from the reference file's own day can belong to it. A
    single candidate is still accepted on any day (counting-through camera,
    or a file re-touched later) - that is unambiguous.
    """
    path, match = find_matching_processed_file(processed_dir, capture_id, reference_mtime, max_delta_seconds)
    if path is None:
        return path, match
    reference_day = datetime.fromtimestamp(reference_mtime).date()
    if capture_time(path).date() == reference_day:
        return path, match
    same_capture = 0
    for other in processed_dir.glob("*.jp*g"):
        parsed = parse_capture_filename(other.name)
        if parsed and parsed.capture_id == capture_id:
            same_capture += 1
            if same_capture > 1:
                return None, SpeedMatch(None, "missing", "processed_other_day", None)
    return path, match


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


def parse_speedshot_log(lines: list[str]) -> dict[tuple[str, date], float]:
    """(capture_id, day) -> km/h. The counter restarts daily, so the number alone is not unique."""
    entries: dict[tuple[str, date], float] = {}
    for line in lines:
        match = SPEEDSHOT_LINE_RE.match(line)
        if not match:
            continue
        try:
            day = datetime.strptime(match.group("day"), "%d.%m.%Y").date()
        except ValueError:
            continue
        entries[(match.group("capture").zfill(5), day)] = float(match.group("kmh").replace(",", "."))
    return entries


def speed_from_speedshot_log(log_path: Path | None, capture_id: str, day: date) -> SpeedMatch:
    if log_path is None:
        return SpeedMatch(None, "missing", "speedshot_log", None)
    try:
        stat = log_path.stat()
    except OSError:
        return SpeedMatch(None, "missing", "speedshot_log", None)
    key = str(log_path)
    cached = _speedshot_cache.get(key)
    if cached and cached[0] == stat.st_size and cached[1] == stat.st_mtime_ns:
        entries = cached[2]
    else:
        try:
            with log_path.open("rb") as handle:
                if stat.st_size > SPEEDSHOT_TAIL_BYTES:
                    handle.seek(stat.st_size - SPEEDSHOT_TAIL_BYTES)
                    handle.readline()  # drop the partial first line
                text = handle.read().decode("latin-1")
        except OSError:
            return SpeedMatch(None, "missing", "speedshot_log", None)
        entries = parse_speedshot_log(text.splitlines())
        _speedshot_cache[key] = (stat.st_size, stat.st_mtime_ns, entries)
    speed = entries.get((capture_id.zfill(5), day))
    if speed is None:
        return SpeedMatch(None, "missing", "speedshot_log", None)
    return SpeedMatch(speed, "ok", "speedshot_log", None)


def timestamp_from_path(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)
