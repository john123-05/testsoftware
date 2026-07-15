from __future__ import annotations

import argparse
import json
import sys

from .asset_sync import AssetSyncWorker
from .config import Settings
from .envfile import write_env_values
from .logging_setup import configure_logging
from .service import LiftpicService
from .supabase_client import SupabaseIngestClient


def _bool_env(value: object) -> str:
    return "true" if bool(value) else "false"


def _config_to_env(config: dict[str, object], device_token: str) -> dict[str, str]:
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


def build_parser() -> argparse.ArgumentParser:
    env_parent = argparse.ArgumentParser(add_help=False)
    env_parent.add_argument("--env", default=".env", help="Path to .env file")

    parser = argparse.ArgumentParser(prog="liftpic-sync", parents=[env_parent])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", parents=[env_parent], help="Run forever")
    sub.add_parser("scan-once", parents=[env_parent], help="Scan and upload one iteration")
    sub.add_parser("health", parents=[env_parent], help="Print local health JSON")
    sub.add_parser("assets", parents=[env_parent], help="Download dashboard-managed local assets once")
    pair = sub.add_parser("pair", parents=[env_parent], help="Pair this PC with a dashboard config")
    pair.add_argument("--code", required=True, help="Pairing code from the staff Liftpic Setup page")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env_file(args.env)
    settings.ensure_dirs()
    configure_logging(settings)

    if args.command == "pair":
        response = SupabaseIngestClient(settings).pair(args.code)
        config = response.get("config") or {}
        device_token = str(response.get("device_token") or "")
        if not isinstance(config, dict) or not device_token:
            raise RuntimeError("pairing response did not include config and device_token")
        write_env_values(args.env, _config_to_env(config, device_token))
        print(json.dumps({"ok": True, "machine_id": config.get("machine_id"), "camera_code": config.get("camera_code")}, indent=2))
        return 0

    service = LiftpicService(settings)
    try:
        if args.command == "run":
            service.run_forever()
            return 0
        if args.command == "scan-once":
            print(json.dumps(service.run_once(), indent=2, sort_keys=True))
            return 0
        if args.command == "health":
            print(json.dumps(service.health(), indent=2, sort_keys=True))
            return 0
        if args.command == "assets":
            result = AssetSyncWorker(settings, service.store).sync_once()
            print(json.dumps(result.__dict__, indent=2, sort_keys=True))
            return 0
    finally:
        service.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
