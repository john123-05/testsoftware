"""Package entry point so `python -m liftpic_sync <command>` works, not only
`python -m liftpic_sync.cli`. Keeps the documented invocation and the recovery
script's `pair` call from failing with 'No module named liftpic_sync.__main__'."""
from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
