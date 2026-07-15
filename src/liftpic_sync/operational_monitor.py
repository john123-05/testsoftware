from __future__ import annotations

import glob
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings


@dataclass(frozen=True)
class OperationalDevice:
    name: str
    kind: str
    status: str
    detail: str
    source_file: str
    last_seen_at: str | None
    severity: str


@dataclass(frozen=True)
class OperationalStatus:
    devices: list[OperationalDevice]
    events: list[dict[str, object]]
    coin_status: str | None
    terminal_status: str | None
    printer_status: str | None
    camera_status: str | None


PROBLEM_RE = re.compile(
    r"(critical|fatal|panic|error|fehler|failed|failure|offline|disabled|"
    r"communication lost|can't connect|cannot connect|not connected|no response|"
    r"timeout|paper empty|printer offline|coinchangererror|validator.*error)",
    re.IGNORECASE,
)
WARNING_RE = re.compile(r"(warn|warning|paper low|low paper|retry|blocked|stoerung|störung)", re.IGNORECASE)
OK_RE = re.compile(
    r"(ready|bereit|ok|connected|enabled|success|successful|image triggered|"
    r"state:\s*(wait|blocking)|terminal bereit|status - ready)",
    re.IGNORECASE,
)
TIMESTAMP_RE = re.compile(
    r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{4})\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2})(?:[.,](?P<millis>\d{1,3}))?"
)


def read_operational_status(settings: Settings) -> OperationalStatus:
    devices: dict[str, OperationalDevice] = {}
    events: list[dict[str, object]] = []

    for path in _iter_log_files(settings.operational_log_globs):
        device = _inspect_log(path, settings)
        if not device:
            continue
        existing = devices.get(device.name)
        if existing is None or _status_priority(device.status) > _status_priority(existing.status):
            devices[device.name] = device
        events.append(_device_event(device))

    ordered = sorted(devices.values(), key=lambda item: item.name)
    return OperationalStatus(
        devices=ordered,
        events=sorted(events, key=lambda item: str(item.get("occurred_at") or ""), reverse=True)[:20],
        coin_status=_status_for(ordered, "cash"),
        terminal_status=_status_for(ordered, "terminal"),
        printer_status=_status_for(ordered, "printer"),
        camera_status=_status_for(ordered, "camera"),
    )


def _iter_log_files(patterns: tuple[str, ...]) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in patterns:
        for match in glob.glob(pattern):
            path = Path(match)
            if path.is_file():
                found[str(path).lower()] = path
    return sorted(found.values(), key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)[:60]


def _inspect_log(path: Path, settings: Settings) -> OperationalDevice | None:
    try:
        stat = path.stat()
    except OSError:
        return None

    lines = _tail_lines(path, max(20, settings.operational_log_tail_lines))
    if not lines:
        return None

    kind = _classify_kind(path, lines)
    if kind == "other":
        return None

    signal_line = _latest_signal_line(lines)
    now = datetime.now(timezone.utc)
    mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
    stale = (now - mtime).total_seconds() > settings.operational_log_stale_minutes * 60
    line_text = signal_line or lines[-1]
    line_at = _parse_line_time(line_text) or mtime.isoformat()

    if signal_line and PROBLEM_RE.search(signal_line):
        status = "down"
        severity = "error"
    elif signal_line and WARNING_RE.search(signal_line):
        status = "degraded"
        severity = "warning"
    elif stale:
        status = "degraded"
        severity = "warning"
        line_text = f"No recent log update since {mtime.isoformat()}"
        line_at = mtime.isoformat()
    else:
        status = "operational"
        severity = "info"

    return OperationalDevice(
        name=_device_name(kind),
        kind=kind,
        status=status,
        detail=line_text.strip()[:240],
        source_file=str(path),
        last_seen_at=line_at,
        severity=severity,
    )


def _tail_lines(path: Path, count: int) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 64_000))
            raw = handle.read()
    except OSError:
        return []
    text = raw.decode("utf-8", errors="replace")
    if text.count("\ufffd") > 8:
        text = raw.decode("latin1", errors="replace")
    return [line for line in text.splitlines() if line.strip()][-count:]


def _classify_kind(path: Path, lines: list[str]) -> str:
    haystack = f"{path} {' '.join(lines[-20:])}".lower()
    if re.search(r"(coin|nri|muenz|münz|cash|barzahlung|coinchanger)", haystack):
        return "cash"
    if re.search(r"(zvt|terminal|kreditkarte|karte|cashless|ec\b|card)", haystack):
        return "terminal"
    if re.search(r"(print|printer|paper|papier|druck)", haystack):
        return "printer"
    if re.search(r"(aida|speed|camera|kamera|camware|tiscapture|image triggered)", haystack):
        return "camera"
    if re.search(r"(error|fehler|warning|warn|offline|disabled)", haystack):
        return "system"
    return "other"


def _latest_signal_line(lines: list[str]) -> str | None:
    for line in reversed(lines[-30:]):
        if PROBLEM_RE.search(line) or WARNING_RE.search(line) or OK_RE.search(line):
            return line
    return None


def _parse_line_time(line: str) -> str | None:
    match = TIMESTAMP_RE.search(line)
    if not match:
        return None
    parts = {key: int(value) if value else 0 for key, value in match.groupdict().items()}
    try:
        return datetime(
            parts["year"],
            parts["month"],
            parts["day"],
            parts["hour"],
            parts["minute"],
            parts["second"],
            parts["millis"] * 1000,
            tzinfo=timezone.utc,
        ).isoformat()
    except ValueError:
        return None


def _device_name(kind: str) -> str:
    return {
        "cash": "Cash / Coin",
        "terminal": "Payment Terminal",
        "printer": "Printer",
        "camera": "Camera / Speed",
        "system": "Machine Logs",
    }.get(kind, "Machine Logs")


def _status_priority(status: str) -> int:
    return {"operational": 1, "degraded": 2, "down": 3}.get(status, 0)


def _status_for(devices: list[OperationalDevice], kind: str) -> str | None:
    relevant = [device for device in devices if device.kind == kind]
    if not relevant:
        return None
    return max(relevant, key=lambda item: _status_priority(item.status)).status


def _device_event(device: OperationalDevice) -> dict[str, object]:
    category = {
        "cash": "cash",
        "terminal": "terminal",
        "printer": "printer",
        "camera": "system",
    }.get(device.kind, "system")
    digest = hashlib.sha1(f"{device.source_file}|{device.detail}".encode("utf-8", errors="replace")).hexdigest()[:12]
    return {
        "id": f"agent-{device.kind}-{digest}",
        "occurred_at": device.last_seen_at,
        "severity": device.severity,
        "category": category,
        "payment_method": "coin" if device.kind == "cash" else "terminal" if device.kind == "terminal" else None,
        "status": "failed" if device.status == "down" else "warning" if device.status == "degraded" else "info",
        "amount_cents": None,
        "amount_kind": "unknown",
        "purchase_signal": "none",
        "description": device.detail,
        "source_file": device.source_file,
        "raw_excerpt": device.detail,
        "device": device.name,
        "tags": ["liftpic-agent", device.kind],
    }
