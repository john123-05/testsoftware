from __future__ import annotations

from pathlib import Path


def _decode_env_bytes(data: bytes) -> str:
    """Decode a .env file that may have been written in UTF-8 or UTF-16.

    Windows tools (older PowerShell defaults, Notepad "Save as Unicode") can
    write .env files as UTF-16, which a naive utf-8 read either mangles or
    fails on. Detect the encoding from a BOM or from interleaved NUL bytes and
    always return clean text with any BOM stripped.
    """
    if data.startswith(b"\xff\xfe"):
        text = data.decode("utf-16-le", errors="replace")
    elif data.startswith(b"\xfe\xff"):
        text = data.decode("utf-16-be", errors="replace")
    elif data.startswith(b"\xef\xbb\xbf"):
        text = data.decode("utf-8-sig", errors="replace")
    elif data.count(0) > max(2, len(data) // 8):
        # No BOM but lots of NUL bytes -> almost certainly UTF-16.
        le_nuls = data[1::2].count(0)
        encoding = "utf-16-le" if le_nuls >= data[0::2].count(0) else "utf-16-be"
        text = data.decode(encoding, errors="replace")
    else:
        text = data.decode("utf-8", errors="replace")
    return text.lstrip("﻿")


def load_env_file(path: str | Path | None) -> dict[str, str]:
    if not path:
        return {}

    env_path = Path(path)
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in _decode_env_bytes(env_path.read_bytes()).splitlines():
        line = raw_line.strip().lstrip("﻿").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def write_env_values(path: str | Path, updates: dict[str, str]) -> None:
    env_path = Path(path)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = dict(updates)
    output: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            output.append(raw_line)
            continue

        key, _ = raw_line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in remaining:
            output.append(f"{normalized_key}={remaining.pop(normalized_key)}")
        else:
            output.append(raw_line)

    if remaining and output and output[-1].strip():
        output.append("")

    for key in sorted(remaining):
        output.append(f"{key}={remaining[key]}")

    env_path.write_text("\n".join(output) + "\n", encoding="utf-8")
