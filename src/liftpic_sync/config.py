from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .envfile import load_env_file, parse_bool


def _get(values: dict[str, str], key: str, default: str = "") -> str:
    return os.environ.get(key, values.get(key, default))


@dataclass(frozen=True)
class Settings:
    app_name: str
    shadow_mode: bool
    park_slug: str
    park_id: str
    customer_code: str
    machine_id: str
    device_token: str
    supabase_functions_url: str
    supabase_url: str
    supabase_anon_key: str
    raw_dir: Path
    processed_dir: Path
    webout_dir: Path | None
    qrcode_dir: Path | None
    upload_source: str
    stage_in_shadow: bool
    statistic_file: Path | None
    print_count_file: Path | None
    app_dir: Path
    state_db: Path
    log_dir: Path
    poll_seconds: float
    file_stable_seconds: float
    speed_match_seconds: float
    speed_timeout_seconds: float
    upload_retry_seconds: float
    heartbeat_seconds: float
    archive_raw: bool

    @classmethod
    def from_env_file(cls, env_path: str | Path | None = None) -> "Settings":
        values = load_env_file(env_path)
        app_dir = Path(_get(values, "APP_DIR", r"C:\liftpic\liftpic-sync"))
        state_db = Path(_get(values, "STATE_DB", str(app_dir / "state" / "liftpic-sync.db")))
        log_dir = Path(_get(values, "LOG_DIR", str(app_dir / "logs")))

        webout = _get(values, "WEBOUT_DIR", r"C:\liftpic\fotos\webout").strip()
        qrcode = _get(values, "QRCODE_DIR", r"C:\liftpic\fotos\qrcode").strip()
        statistic_file = _get(values, "STATISTIC_FILE", r"C:\liftpic\samuel_neu\Statistic.txt").strip()
        print_count_file = _get(values, "PRINT_COUNT_FILE", r"C:\liftpic\samuel_neu\PrintCount.txt").strip()

        return cls(
            app_name=_get(values, "APP_NAME", "liftpic-sync"),
            shadow_mode=parse_bool(_get(values, "SHADOW_MODE", "true"), True),
            park_slug=_get(values, "PARK_SLUG", "unknown-park"),
            park_id=_get(values, "PARK_ID", ""),
            customer_code=_get(values, "CUSTOMER_CODE", "0000"),
            machine_id=_get(values, "MACHINE_ID", "unknown-machine"),
            device_token=_get(values, "DEVICE_TOKEN", ""),
            supabase_functions_url=_get(values, "SUPABASE_FUNCTIONS_URL", "").rstrip("/"),
            supabase_url=_get(values, "SUPABASE_URL", "").rstrip("/"),
            supabase_anon_key=_get(values, "SUPABASE_ANON_KEY", ""),
            raw_dir=Path(_get(values, "RAW_DIR", r"C:\liftpic\fotos")),
            processed_dir=Path(_get(values, "PROCESSED_DIR", r"C:\liftpic\fotos\out")),
            webout_dir=Path(webout) if webout else None,
            qrcode_dir=Path(qrcode) if qrcode else None,
            upload_source=_get(values, "UPLOAD_SOURCE", "qrcode").strip().lower(),
            stage_in_shadow=parse_bool(_get(values, "STAGE_IN_SHADOW", "false"), False),
            statistic_file=Path(statistic_file) if statistic_file else None,
            print_count_file=Path(print_count_file) if print_count_file else None,
            app_dir=app_dir,
            state_db=state_db,
            log_dir=log_dir,
            poll_seconds=float(_get(values, "POLL_SECONDS", "2")),
            file_stable_seconds=float(_get(values, "FILE_STABLE_SECONDS", "2")),
            speed_match_seconds=float(_get(values, "SPEED_MATCH_SECONDS", "12")),
            speed_timeout_seconds=float(_get(values, "SPEED_TIMEOUT_SECONDS", "30")),
            upload_retry_seconds=float(_get(values, "UPLOAD_RETRY_SECONDS", "15")),
            heartbeat_seconds=float(_get(values, "HEARTBEAT_SECONDS", "60")),
            archive_raw=parse_bool(_get(values, "ARCHIVE_RAW", "false"), False),
        )

    def ensure_dirs(self) -> None:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.state_db.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
