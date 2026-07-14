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
