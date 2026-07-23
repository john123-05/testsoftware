from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalStatus:
    paper_printed: int | None
    paper_capacity: int | None
    paper_remaining: int | None
    paper_status: str
    statistic_file_size: int | None
    statistic_last_line: str | None


def read_local_status(
    statistic_file: Path | None,
    print_count_file: Path | None,
    paper_capacity: int = 0,
    paper_warn_remaining: int = 20,
) -> LocalStatus:
    # PrintCount.txt counts printed photos UP; a paper roll holds a fixed
    # capacity. Remaining = capacity - printed. When the roll is changed the
    # legacy print software resets its counter, so remaining follows naturally.
    printed = _read_int_file(print_count_file)
    capacity = paper_capacity if paper_capacity and paper_capacity > 0 else None
    remaining = max(0, capacity - printed) if capacity is not None and printed is not None else None

    statistic_size = None
    statistic_last_line = None
    if statistic_file and statistic_file.exists():
        try:
            statistic_size = statistic_file.stat().st_size
            statistic_last_line = _tail_last_line(statistic_file)
        except OSError:
            statistic_size = None

    return LocalStatus(
        paper_printed=printed,
        paper_capacity=capacity,
        paper_remaining=remaining,
        paper_status=_paper_status(remaining, paper_warn_remaining),
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


def _paper_status(remaining: int | None, warn_remaining: int = 20) -> str:
    if remaining is None:
        return "unknown"
    if remaining <= 0:
        return "empty"
    if remaining <= max(0, warn_remaining):
        return "low"
    return "ok"
