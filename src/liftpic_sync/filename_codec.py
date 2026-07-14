from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


LEGACY_RE = re.compile(r"^(?P<legacy>\d{4})(?P<time>\d{8})(?P<file>\d{4})\.jpe?g$", re.I)
PROCESSED_RE = re.compile(
    r"^(?P<capture>\d{5})_?(?P<stamp>\d{14})(?P<speed>\d{4})\.jpe?g$",
    re.I,
)
RAW_RE = re.compile(r"^(?P<capture>\d{1,8})\.jpe?g$", re.I)


@dataclass(frozen=True)
class LegacyName:
    filename: str
    legacy_code: str
    time_code: str
    file_code: str


@dataclass(frozen=True)
class CaptureName:
    capture_id: str
    timestamp: datetime | None
    speed_kmh: float | None
    speed_code: str | None


def parse_legacy_filename(filename: str) -> LegacyName | None:
    match = LEGACY_RE.match(Path(filename).name)
    if not match:
        return None
    return LegacyName(
        filename=Path(filename).name,
        legacy_code=match.group("legacy"),
        time_code=match.group("time"),
        file_code=match.group("file"),
    )


def parse_capture_filename(filename: str) -> CaptureName | None:
    name = Path(filename).name
    processed = PROCESSED_RE.match(name)
    if processed:
        stamp = processed.group("stamp")
        timestamp = datetime.strptime(stamp, "%Y%m%d%H%M%S")
        speed_code = processed.group("speed")
        return CaptureName(
            capture_id=processed.group("capture").zfill(5),
            timestamp=timestamp,
            speed_kmh=_speed_code_to_kmh(speed_code),
            speed_code=speed_code,
        )

    raw = RAW_RE.match(name)
    if raw:
        return CaptureName(
            capture_id=raw.group("capture").zfill(5),
            timestamp=None,
            speed_kmh=None,
            speed_code=None,
        )
    return None


def build_legacy_filename(
    *,
    customer_code: str,
    capture_id: str,
    captured_at: datetime,
    extension: str = ".jpg",
) -> LegacyName:
    customer = _four_digits(customer_code)
    time_code = captured_at.strftime("%d%m%Y")
    file_code = _short_capture_code(capture_id)
    mixed = mix_customer_time_capture(customer, time_code, file_code)
    filename = f"{mixed}{extension.lower()}"
    return LegacyName(
        filename=filename,
        legacy_code=mixed[:4],
        time_code=time_code,
        file_code=file_code,
    )


def mix_customer_time_capture(customer_code: str, time_code: str, file_code: str) -> str:
    """Old jpeg4web/Liftpic interleaving formula.

    C++ source note:
    N[0]+T[1]+Z[2]+N[2]+T[0]+Z[1]+T[7]+T[3]+
    N[1]+N[3]+Z[0]+T[5]+T[4]+T[2]+T[6]+Z[3]
    """
    n = _four_digits(customer_code)
    t = re.sub(r"\D", "", time_code or "")[:8].zfill(8)
    z = re.sub(r"\D", "", file_code or "")[-4:].zfill(4)
    return (
        n[0] + t[1] + z[2] + n[2]
        + t[0] + z[1] + t[7] + t[3]
        + n[1] + n[3] + z[0] + t[5]
        + t[4] + t[2] + t[6] + z[3]
    )


def _four_digits(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return "0000"
    return digits[:4].zfill(4)


def _short_capture_code(capture_id: str) -> str:
    digits = re.sub(r"\D", "", capture_id or "")
    if len(digits) >= 5:
        return digits[-5:][1:]
    return digits[-4:].zfill(4)


def _speed_code_to_kmh(speed_code: str) -> float | None:
    try:
        value = int(speed_code)
    except ValueError:
        return None
    # AidaTest examples encode 1395 as 13.95 km/h.
    return round(value / 100.0, 2)
