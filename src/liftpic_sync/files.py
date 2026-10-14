from __future__ import annotations

import hashlib
import time
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg"}


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def is_stable(path: Path, stable_seconds: float) -> bool:
    try:
        first_size = path.stat().st_size
        first_mtime = path.stat().st_mtime
    except OSError:
        return False
    if time.time() - first_mtime < stable_seconds:
        return False
    time.sleep(0.05)
    try:
        second_size = path.stat().st_size
        second_mtime = path.stat().st_mtime
    except OSError:
        return False
    return first_size == second_size and first_mtime == second_mtime


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ChecksumCache:
    """sha256 per file, recomputed only when size or mtime change.

    The scan loop runs every few seconds over the same files; without this,
    every already-known file would be re-read from disk on every pass.
    """

    MAX_ENTRIES = 20_000

    def __init__(self) -> None:
        self._entries: dict[str, tuple[tuple[int, int], str]] = {}

    def get(self, path: Path) -> str:
        stat = path.stat()
        signature = (stat.st_size, stat.st_mtime_ns)
        key = str(path)
        cached = self._entries.get(key)
        if cached and cached[0] == signature:
            return cached[1]
        if len(self._entries) >= self.MAX_ENTRIES:
            self._entries.clear()
        value = sha256_file(path)
        self._entries[key] = (signature, value)
        return value
