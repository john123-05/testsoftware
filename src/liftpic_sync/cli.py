from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .asset_sync import AssetSyncWorker
from .config import Settings
from .envfile import write_env_values
from .logging_setup import configure_logging
from .remote_config import config_to_env
from .service import LiftpicService
from .supabase_client import SupabaseIngestClient


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


def _acquire_single_instance_lock(lock_path: Path):
    """Hold an OS-level exclusive lock for the whole process lifetime so a second
    'run' instance can't start and fight the first over the shared state DB and
    photo folders (the root cause of two concurrent agents seen on the Imst PC).
    The lock releases automatically when the process dies (the fd closes), so a
    crash never leaves a stale lock behind - unlike a PID file. Returns the open
    handle to keep alive, None if another instance already holds it, or a dummy
    sentinel if the lock file can't be opened (never block startup for that)."""
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+")
    except OSError:
        return True  # truthy sentinel: proceed unlocked rather than block startup
    try:
        if sys.platform.startswith("win"):
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


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
        write_env_values(args.env, config_to_env(config, device_token))
        print(json.dumps({"ok": True, "machine_id": config.get("machine_id"), "camera_code": config.get("camera_code")}, indent=2))
        return 0

    lock_handle = None
    if args.command == "run":
        lock_handle = _acquire_single_instance_lock(Path(settings.state_db).parent / "liftpic-sync.lock")
        if lock_handle is None:
            logging.getLogger("liftpic_sync.cli").error(
                "another liftpic-sync instance is already running (single-instance lock held) - "
                "exiting; the existing agent keeps running"
            )
            return 0

    service = LiftpicService(settings, env_path=args.env)
    try:
        if args.command == "run":
            # keep lock_handle referenced for the whole run so the lock is held
            assert lock_handle is not None
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
