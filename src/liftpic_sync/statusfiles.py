from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalStatus:
    paper_remaining: int | None
    paper_status: str
    statistic_file_size: int | None
    statistic_last_line: str | None


def read_local_status(statistic_file: Path | None, print_count_file: Path | None) -> LocalStatus:
    paper_remaining = _read_int_file(print_count_file)
    statistic_size = None
    statistic_last_line = None

    if statistic_file and statistic_file.exists():
        try:
            statistic_size = statistic_file.stat().st_size
            statistic_last_line = _tail_last_line(statistic_file)
        except OSError:
            statistic_size = None

    return LocalStatus(
        paper_remaining=paper_remaining,
        paper_status=_paper_status(paper_remaining),
        statistic_file_size=statistic_size,
        statistic_last_line=statistic_last_line,
    )


def _read_int_file(path: Path | None) -> int | None:
    if not path or not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits) if digits else None


def _tail_last_line(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else None


def _paper_status(remaining: int | None) -> str:
    if remaining is None:
        return "unknown"
    if remaining <= 0:
        return "empty"
    if remaining <= 20:
        return "low"
    return "ok"
