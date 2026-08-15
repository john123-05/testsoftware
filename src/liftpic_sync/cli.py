from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .asset_sync import AssetSyncWorker
from .config import Settings
from .envfile import write_env_values
from .logging_setup import configure_logging
from .remote_config import config_to_env
from .service import LiftpicService
from .supabase_client import SupabaseIngestClient


log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    env_parent = argparse.ArgumentParser(add_help=False)
    env_parent.add_argument("--env", default=".env", help="Path to .env file")

    # --env lives only on the subcommand parsers, not here too. argparse merges
    # both into the same "env" dest when a value is supplied before the
    # subcommand name, but the subcommand parser's own default silently wins
    # and overwrites it - "--env X pair --code Y" quietly resolves to the
    # default ".env" instead of X, with no error. Keeping --env off the top
    # level makes that invocation order fail loudly instead of pairing/running
    # against an empty config.
    parser = argparse.ArgumentParser(prog="liftpic-sync")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", parents=[env_parent], help="Run forever")
    sub.add_parser("scan-once", parents=[env_parent], help="Scan and upload one iteration")
    sub.add_parser("health", parents=[env_parent], help="Print local health JSON")
    sub.add_parser(
        "preflight", parents=[env_parent],
        help="Show what this PC looks like before switching anything (read-only)",
    )
    sub.add_parser("assets", parents=[env_parent], help="Download dashboard-managed local assets once")
    pair = sub.add_parser("pair", parents=[env_parent], help="Pair this PC with a dashboard config")
    pair.add_argument("--code", required=True, help="Pairing code from the staff Liftpic Setup page")
    purge = sub.add_parser("purge-date", parents=[env_parent], help="Delete local photo+ride events for one business date (cleanup)")
    purge.add_argument("--date", required=True, help="Business date YYYY-MM-DD to purge from local state")
    return parser


def _singleton_lock_path(settings) -> Path:
    """A single, install-independent lock location so two agents from *different*
    install folders still exclude each other. The old per-state-DB lock only
    guarded one folder, so a second install (the empty-.env re-install) ran a
    rogue upload instance with a stale token - the recurring 401 outage. On
    Windows the file lock is a system-wide kernel object, so it works across
    user sessions (scheduled task vs. manual run) too."""
    if sys.platform.startswith("win"):
        base = os.environ.get("ProgramData") or r"C:\ProgramData"
        return Path(base) / "liftpic-sync" / "singleton.lock"
    return Path(settings.state_db).parent / "liftpic-sync.lock"


def _ausweich_lock_pfad() -> Path | None:
    """Ein Sperrpfad, den auch ein normaler Benutzer beschreiben darf.

    Die Sperre unter ProgramData ist systemweit und deshalb der richtige Ort -
    aber genau dort scheiterte sie: die Datei wurde einmal vom Konto SYSTEM
    angelegt, seither laeuft der Agent als Benutzer und darf sie nicht mehr
    oeffnen. Dieser Ausweichpfad schuetzt wenigstens gegen zwei Agenten
    desselben Benutzers.
    """
    if not sys.platform.startswith("win"):
        return None
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    return Path(base) / "liftpic-sync" / "singleton.lock"


class Sperrergebnis:
    """Genau drei Ausgaenge, ausdruecklich benannt statt aus `None` geraten.

    * `gesperrt`  - wir halten die Sperre, alles in Ordnung.
    * `belegt`    - ein anderer Agent haelt sie. Wir beenden uns.
    * `ungesichert` - die Sperrdatei liess sich nirgends anlegen. Wir laufen
      weiter, melden es aber (F-024).
    """

    def __init__(self, zustand: str, handle=None, grund: str = ""):
        self.zustand = zustand
        self.handle = handle
        self.grund = grund

    @property
    def gesperrt(self) -> bool:
        return self.zustand == "gesperrt"

    @property
    def belegt(self) -> bool:
        return self.zustand == "belegt"

    @property
    def ungesichert(self) -> bool:
        return self.zustand == "ungesichert"


def _sperre_versuchen(lock_path: Path):
    """Ein einzelner Sperrversuch. Handle, None (belegt) oder ein Fehlertext."""
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+")
    except OSError as exc:
        return f"{lock_path}: {exc}"
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


def _acquire_single_instance_lock(lock_path: Path) -> Sperrergebnis:
    """Verhindern, dass ein zweiter Agent neben dem ersten laeuft.

    Die Sperre ist ein Kernel-Objekt und wird beim Prozessende automatisch
    freigegeben - ein Absturz hinterlaesst also nie eine verwaiste Sperre,
    anders als eine PID-Datei.

    Was diese Fassung anders macht (F-024):

    Frueher hiess der Fehlerfall `except OSError: return True` - der Agent lief
    ungeschuetzt weiter und sagte **niemandem** etwas davon. Genau das passierte
    seit dem 08.08.2026: die Sperrdatei unter ProgramData gehoert SYSTEM, der
    Agent laeuft als Benutzer, `open()` scheitert - und die Sperre hat seither
    nie wieder jemanden abgewiesen, ohne dass es irgendwo auffiel.

    Jetzt wird bei einem Rechteproblem auf LOCALAPPDATA ausgewichen. Scheitert
    auch das, laeuft der Agent weiter - eine produktive Anlage darf nie an einem
    Rechteproblem stehenbleiben -, aber der ungeschuetzte Zustand wird
    zurueckgemeldet und landet im Verlauf. Die eigentliche Absicherung gegen
    Doppelarbeit liegt ohnehin tiefer, im atomaren Anspruch auf Uploads und
    Auftraege; die Sperre ist die erste, nicht die einzige Verteidigung.
    """
    ergebnis = _sperre_versuchen(lock_path)
    if not isinstance(ergebnis, str):
        return Sperrergebnis("gesperrt", ergebnis) if ergebnis else Sperrergebnis("belegt")

    erster_fehler = ergebnis
    ausweich = _ausweich_lock_pfad()
    if ausweich is not None and ausweich != lock_path:
        zweiter = _sperre_versuchen(ausweich)
        if not isinstance(zweiter, str):
            log.warning(
                "singleton lock: %s not usable, fell back to %s", erster_fehler, ausweich
            )
            return Sperrergebnis("gesperrt", zweiter) if zweiter else Sperrergebnis("belegt")
        erster_fehler = f"{erster_fehler} / {zweiter}"

    grund = (
        "Doppelstart-Schutz nicht aktiv: die Sperrdatei liess sich nirgends "
        f"anlegen ({erster_fehler}). Der Automat arbeitet normal weiter, aber "
        "ein zweiter Agent koennte unbemerkt danebenlaufen."
    )
    log.error("%s", grund)
    return Sperrergebnis("ungesichert", grund=grund)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env_file(args.env)

    if args.command == "preflight":
        # Bewusst VOR ensure_dirs und configure_logging: der Bericht soll den
        # PC so zeigen, wie er ist, und dabei weder Ordner anlegen noch in ein
        # Protokoll schreiben. Auch die Code-Vorschrift wird angewandt, damit
        # dort steht, was im Betrieb wirklich gelten wuerde.
        #
        # Protokollausgaben werden dabei stummgeschaltet: die Abweichung der
        # Kundennummer steht im Bericht selbst, deutlicher als eine Warnzeile
        # quer durch die Ausgabe.
        import logging

        from .preflight import bericht

        logging.disable(logging.CRITICAL)
        try:
            print(bericht(settings.with_viewer_recipe()))
        finally:
            logging.disable(logging.NOTSET)
        return 0

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

    if args.command == "purge-date":
        from .state import StateStore

        store = StateStore(settings.state_db)
        try:
            photos, rides = store.purge_business_date(args.date)
        finally:
            store.close()
        print(json.dumps({"ok": True, "date": args.date, "purged_photo_events": photos, "purged_ride_events": rides}, indent=2))
        return 0

    # Die Sperre gilt fuer jeden Befehl, der wirklich arbeitet - nicht nur fuer
    # `run`. `scan-once` laedt vollstaendig hoch und `assets` schreibt Dateien
    # ins Verkaufsprogramm; beide sind neben einem laufenden Agenten ein
    # Zweitagent. `purge-date` loescht Zeilen, die er gerade verarbeitet.
    sperre = None
    if args.command in ("run", "scan-once", "assets"):
        sperre = _acquire_single_instance_lock(_singleton_lock_path(settings))
        if sperre.belegt:
            log.error(
                "another liftpic-sync instance is already running (single-instance lock held) - "
                "exiting; the existing agent keeps running (this pid %s)", os.getpid(),
            )
            return 0

    service = LiftpicService(settings, env_path=args.env)
    try:
        if args.command == "run":
            # Die Sperre haengt am offenen Handle: solange `sperre` referenziert
            # bleibt, bleibt sie gehalten.
            if sperre is not None and sperre.ungesichert:
                # Ungeschuetzt weiterlaufen ist erlaubt - aber es muss im
                # Dashboard stehen, nicht nur im Protokoll (F-024).
                service.store.record_health_event(
                    kind="uploader", severity="warning",
                    summary="Doppelstart-Schutz nicht aktiv",
                    detail=sperre.grund,
                )
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
