from __future__ import annotations

import argparse
import json
import sys

from .config import Settings
from .logging_setup import configure_logging
from .service import LiftpicService


def build_parser() -> argparse.ArgumentParser:
    env_parent = argparse.ArgumentParser(add_help=False)
    env_parent.add_argument("--env", default=".env", help="Path to .env file")

    parser = argparse.ArgumentParser(prog="liftpic-sync", parents=[env_parent])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", parents=[env_parent], help="Run forever")
    sub.add_parser("scan-once", parents=[env_parent], help="Scan and upload one iteration")
    sub.add_parser("health", parents=[env_parent], help="Print local health JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env_file(args.env)
    settings.ensure_dirs()
    configure_logging(settings)
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
    finally:
        service.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
