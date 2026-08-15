from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import Settings


def configure_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.log_dir / "liftpic-sync.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    # Die Prozessnummer gehoert ins Format (F-026).
    #
    # Ohne sie sieht Doppelbetrieb im Protokoll aus wie ein einzelner Agent, der
    # jede Sache zweimal tut - in 11 MB Protokoll war kein Verdachtsfall
    # entscheidbar. Genau deshalb wurde die Stoerung am Imster Automaten
    # monatelang als "401-Problem" gelesen statt als zwei Agenten. Sie ist auch
    # die einzige Moeglichkeit, die Wirkung der Sperre zu ueberpruefen.
    formatter = logging.Formatter(
        "%(asctime)s pid=%(process)d %(levelname)s %(name)s: %(message)s"
    )

    file_handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
