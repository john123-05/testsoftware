"""Mapping between the dashboard's machine config and local .env values.

Used by both `pair` (first-time setup) and the in-service config refresh so
dashboard changes (shadow mode, upload mode, folder paths, ...) reach a running
PC without re-running the installer.
"""
from __future__ import annotations


def _bool_env(value: object) -> str:
    return "true" if bool(value) else "false"


def config_to_env(config: dict[str, object], device_token: str) -> dict[str, str]:
    mode = str(config.get("mode") or "sold_only")
    upload_source = "qrcode"
    if mode == "all_photos":
        upload_source = "processed"
    if mode == "count_only":
        upload_source = "processed"

    shadow_mode = bool(config.get("shadow_mode"))
    if mode == "count_only":
        shadow_mode = True

    return {
        "PARK_SLUG": str(config.get("park_slug") or "unknown-park"),
        "PARK_ID": str(config.get("park_id") or ""),
        "CUSTOMER_CODE": str(config.get("legacy_customer_code") or "0000"),
        "MACHINE_ID": str(config.get("machine_id") or "unknown-machine"),
        "CAMERA_CODE": str(config.get("camera_code") or "default"),
        "DEVICE_TOKEN": device_token,
        "SHADOW_MODE": _bool_env(shadow_mode),
        "RAW_DIR": str(config.get("raw_dir") or r"C:\liftpic\fotos"),
        "PROCESSED_DIR": str(config.get("processed_dir") or r"C:\liftpic\fotos\out"),
        "WEBOUT_DIR": str(config.get("webout_dir") or r"C:\liftpic\fotos\webout"),
        "QRCODE_DIR": str(config.get("qrcode_dir") or r"C:\liftpic\fotos\qrcode"),
        "STATISTIC_FILE": str(config.get("statistic_file") or r"C:\liftpic\samuel_neu\Statistic.txt"),
        "PRINT_COUNT_FILE": str(config.get("print_count_file") or r"C:\liftpic\samuel_neu\PrintCount.txt"),
        "UPLOAD_SOURCE": upload_source,
        "RIDE_COUNT_ENABLED": _bool_env(config.get("count_rides_enabled") is not False),
    }
