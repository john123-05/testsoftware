from __future__ import annotations

import logging
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from .asset_sync import AssetSyncWorker
from .config import Settings
from .envfile import load_env_file, write_env_values
from .operational_monitor import RELAY_MARKER, read_operational_status
from .remote_config import config_to_env
from .ride_tracker import RideTracker
from .scanner import FolderScanner
from .state import StateStore
from .statusfiles import read_local_status
from .payments import read_payments
from .system_probe import collect_probes
from .test_photo_upload import NichtZuordenbar, lade_testfoto_hoch
from .supabase_client import SupabaseIngestClient
from .uploader import UploadWorker
from .viewer_control import (
    find_program, in_night_window, laeuft_ohne_bildschirm, restart_program,
    restartable_programs, trigger_test_photo,
)
from . import __version__


log = logging.getLogger(__name__)


# Wie alt ein Sofort-Auftrag hoechstens sein darf, bevor er verfaellt. Grosszuegig
# genug fuer einen Automaten, der kurz offline war, eng genug, dass niemand von
# einem Neustart ueberrascht wird, den er laengst vergessen hat.
AUFTRAG_MAX_ALTER_MINUTEN = 30


# Wie oft sich der Automat hoechstens neu koppelt, bevor er aufgibt und es
# meldet. Bei zwei Instanzen koppeln beide im Wechsel und entwerten sich das
# Token gegenseitig - das lief frueher endlos alle 120 Sekunden weiter.
# Zehn Versuche sind gut zwanzig Minuten; laenger ist es kein Aussetzer mehr.
AUTH_REPARATUR_MAX = 10


# Stoerungen, die ein laufender Prozess nicht heilen kann.
#
# Sonst gilt: laeuft das Programm noch, beschreibt eine Fehlerzeile ein Problem
# IM Programm, nicht MIT ihm - dann ist Gelb richtig. "Device lost" ist die
# Ausnahme. 3GerTis laeuft danach unveraendert weiter, nimmt aber nie wieder ein
# Bild auf, weil es mit restart_if_lost=0 nicht neu verbindet. Am 15.08.2026
# stand die Kachel deshalb auf Gelb, waehrend 40 Minuten spaeter ein Testfoto
# ins Leere lief.
PROZESS_HILFT_NICHT = re.compile(
    r"(device lost|geraet verloren|gerät verloren)",
    re.IGNORECASE,
)


def _auftragsalter_minuten(request: dict) -> float | None:
    """Wie viele Minuten der Auftrag alt ist, oder None wenn unbekannt."""
    roh = request.get("requested_at")
    if not isinstance(roh, str) or not roh.strip():
        return None
    try:
        # Supabase liefert ISO mit 'Z'; fromisoformat kennt das erst ab 3.11.
        gestellt = datetime.fromisoformat(roh.replace("Z", "+00:00"))
    except ValueError:
        return None
    if gestellt.tzinfo is None:
        return None
    jetzt = datetime.now(gestellt.tzinfo)
    return max(0.0, (jetzt - gestellt).total_seconds() / 60.0)


def _juengstes_bild(ordner) -> Path | None:
    """Das zuletzt geschriebene Bild in einem Ordner."""
    if ordner is None or not Path(ordner).is_dir():
        return None
    bilder = [
        p for p in Path(ordner).iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg")
    ]
    if not bilder:
        return None
    return max(bilder, key=lambda p: p.stat().st_mtime)


def _reconcile(devices, probes: list[dict], online: bool = True) -> list[dict]:
    """Gemessenes schlaegt Interpretiertes.

    Wenn direkt gemessen wurde, dass ein Programm laeuft, darf eine Zeile aus
    seiner Protokolldatei es nicht als ausgefallen melden. Die Zeile beschreibt
    dann ein Problem IM Programm, nicht MIT ihm - und genau diese Verwechslung
    liess das Verkaufsprogramm als tot erscheinen, waehrend es lief und
    lediglich den fehlenden Muenzpruefer meldete.

    Dasselbe gilt fuer die Leitung: eine gescheiterte Internetpruefung von heute
    Nacht sagt nichts darueber, ob gerade eine Verbindung besteht. Wenn wir in
    diesem Moment mit dem Server sprechen, ist sie da - und der alte Eintrag
    gehoert in die Vergangenheitsform, nicht auf Rot.

    Eine Ausnahme bleibt: manche Stoerungen kann ein laufender Prozess gar
    nicht heilen. Verliert die Kamera ihr Geraet, laeuft 3GerTis munter weiter
    und nimmt trotzdem nie wieder ein Bild auf - `restart_if_lost=0`, es
    verbindet sich nicht von allein neu. Solche Zeilen duerfen nicht
    heruntergestuft werden, sonst steht Gelb, wo Rot hingehoert.
    """
    laufend = {
        p.get("name", "").lower()
        for p in probes
        if p.get("kind") == "process" and p.get("status") == "ok"
    }

    ergebnis: list[dict] = []
    for device in devices:
        eintrag = dict(device.__dict__)
        name = eintrag.get("name", "")
        # Klarname aus Protokoll und Messung sind bewusst identisch benannt
        # ("Kamera-Software" hier wie dort), damit sie hier zusammenfinden. Der
        # split bleibt fuer aeltere Eintraege stehen, die den Technikzusatz noch
        # im Namen trugen.
        basis = name.split("(")[0].strip().lower()
        unheilbar = bool(PROZESS_HILFT_NICHT.search(eintrag.get("detail", "") or ""))
        if eintrag.get("status") == "down" and basis in laufend and not unheilbar:
            eintrag["status"] = "degraded"
            eintrag["severity"] = "warning"
            eintrag["detail"] = f"Programm laeuft, meldet aber: {eintrag.get('detail', '')}"
        elif eintrag.get("kind") == "network" and online:
            eintrag["status"] = "operational"
            eintrag["severity"] = "info"
            eintrag["plain"] = (
                "Aktuell verbunden. Zwischenzeitlich gab es eine Unterbrechung."
            )
        ergebnis.append(eintrag)
    return ergebnis


class LiftpicService:
    def __init__(self, settings: Settings, env_path: str | None = None):
        # The viewer's configuration decides what the printed QR contains, so it
        # overrides ours before anything is computed from it.
        self.settings = settings.with_viewer_recipe()
        self.env_path = env_path
        self.settings.ensure_dirs()
        self.store = StateStore(settings.state_db)
        self._build_workers()
        self._last_heartbeat = 0.0
        # Wall-clock time of the last heartbeat that actually reached the server.
        # The watchdog exits the process if this goes stale (see _check_watchdog).
        self._last_heartbeat_ok = time.time()
        # Wall-clock time of the last successful upload; the upload watchdog uses
        # it to catch a dead upload path even while heartbeats keep flowing.
        self._last_upload_ok = time.time()
        # Throttle for the device-token self-repair so a bad token can't trigger
        # a re-pair on every single loop iteration.
        self._last_auth_repair = 0.0
        # Wie oft die Selbstheilung schon vergeblich versucht wurde, und ob wir
        # es bereits gemeldet haben (F-025).
        self._auth_repairs = 0
        self._auth_repair_gemeldet = False
        self._last_asset_sync = 0.0
        self._last_config_refresh = 0.0
        self._last_payment_scan = 0.0
        self._payment_cache: dict = {}
        # Schon gemeldete Auffaelligkeiten, damit dieselbe Abweichung nicht bei
        # jedem Heartbeat erneut als neuer Vorfall im Verlauf landet.
        self._gemeldete_zahlungen: set[str] = set()
        # Id of a restart order already carried out but not yet acknowledged to
        # the server. Sent with the next asset poll.
        self._pending_restart_ack: str | None = None
        # Start and cause of an ongoing outage, so the reconnect can report how
        # long the PC was cut off and why. Kept in the state DB rather than only
        # in memory: an outage that coincides with a restart (power cut,
        # watchdog) would otherwise lose its start time, and the reconnect could
        # not say how long the machine had been unreachable.
        stored_since = self.store.get_app_state("offline_since")
        self._offline_since: float | None = float(stored_since) if stored_since else None
        self._offline_reason: str | None = self.store.get_app_state("offline_reason")
        if self._offline_since is not None:
            log.warning(
                "starting up while an outage from %s is still open - will report it on reconnect",
                datetime.fromtimestamp(self._offline_since).isoformat(timespec="seconds"),
            )
        # Health notes already reported this run, so a standing fault is noted
        # once instead of on every single scan.
        self._reported_faults: set[str] = set()
        # Machine probes are expensive (PowerShell, sockets), so they are run at
        # heartbeat pace and reused by the loop in between.
        self._probe_cache: list[dict] | None = None
        self._last_probe = 0.0

    def _build_workers(self) -> None:
        self.ride_tracker = RideTracker(self.settings, self.store)
        self.scanner = FolderScanner(self.settings, self.store)
        self.uploader = UploadWorker(self.settings, self.store)
        self.asset_sync = AssetSyncWorker(self.settings, self.store)
        self.client = SupabaseIngestClient(self.settings)

    def close(self) -> None:
        self.store.close()

    def run_forever(self) -> None:
        log.info(
            "starting %s for park=%s machine=%s shadow=%s watchdog=%ss",
            self.settings.app_name,
            self.settings.park_slug,
            self.settings.machine_id,
            self.settings.shadow_mode,
            self.settings.watchdog_seconds,
        )
        self._last_heartbeat_ok = time.time()
        while True:
            self._refresh_config_if_due()
            try:
                self.run_once()
            except Exception:
                # Never let one bad cycle kill the loop; the watchdog below
                # handles a *persistent* failure by exiting for a clean restart.
                log.exception("run_once failed")
            self._check_watchdog()
            time.sleep(self.settings.poll_seconds)

    def _check_watchdog(self) -> None:
        """Exit(1) if no heartbeat has reached the server for watchdog_seconds, so
        the scheduled task's restart-on-failure recovers us with a fresh process.
        This turns a *silent hang* (connection dead but process alive) into an
        automatic recovery instead of hours of unnoticed downtime."""
        if self.settings.watchdog_seconds <= 0:
            return
        stalled_for = time.time() - self._last_heartbeat_ok
        if stalled_for > self.settings.watchdog_seconds:
            log.critical(
                "connection watchdog: no successful heartbeat for %.0fs (limit %.0fs) - "
                "exiting(1) so the scheduled task restarts a fresh process",
                stalled_for,
                self.settings.watchdog_seconds,
            )
            raise SystemExit(1)

        # Upload-stall watchdog: fresh photos are queued but none have uploaded
        # for too long (a dead/hung upload path the heartbeat can't see). Only
        # "queued" work counts, never "retry" - dead retries (source file gone)
        # would otherwise keep this tripping forever in a restart loop.
        if self.settings.upload_stall_seconds > 0:
            queued = int(self.store.counts().get("queued", 0))
            if queued > 0 and (time.time() - self._last_upload_ok) > self.settings.upload_stall_seconds:
                log.critical(
                    "upload watchdog: %s photos queued but no upload succeeded for >%.0fs - "
                    "exiting(1) for a clean restart",
                    queued,
                    self.settings.upload_stall_seconds,
                )
                raise SystemExit(1)

    def _repair_auth(self) -> None:
        """Uploads were rejected on auth (401/403) -> the device token is stale
        or empty. Re-pair with the stored pairing code to fetch a fresh token
        and apply it live. This is the self-heal for the recurring "uploads
        silently rejected" outage; throttled so it runs at most every ~2 min."""
        if not self.env_path or not self.settings.pairing_code:
            return
        now = time.time()
        if now - self._last_auth_repair < 120:
            return

        # Nicht endlos neu koppeln (F-025).
        #
        # Bei zwei Instanzen koppeln beide im Wechsel und entwerten sich dabei
        # gegenseitig das Token - alle 120 Sekunden, endlos. Genau so sah die
        # wiederkehrende 401-Stoerung aus, und sie wurde monatelang als
        # Serverproblem gelesen. Nach einigen erfolglosen Versuchen ist die
        # Selbstheilung nicht mehr die Antwort; dann muss jemand hinsehen.
        self._auth_repairs += 1
        if self._auth_repairs > AUTH_REPARATUR_MAX:
            if not self._auth_repair_gemeldet:
                self._auth_repair_gemeldet = True
                log.error(
                    "auth self-repair: %d attempts without success - giving up; "
                    "this looks like two agents invalidating each other's token",
                    self._auth_repairs,
                )
                self.store.record_health_event(
                    kind="uploader", severity="error",
                    summary="Anmeldung am Server schlaegt dauerhaft fehl",
                    detail=(
                        f"Der Automat hat sich {self._auth_repairs}-mal neu "
                        "gekoppelt und wird weiterhin abgewiesen. Haeufigste "
                        "Ursache: ein zweiter Agent koppelt gegen denselben "
                        "Datensatz und entwertet dabei das Token."
                    ),
                )
            return

        self._last_auth_repair = now
        try:
            response = self.client.pair(self.settings.pairing_code)
            config = response.get("config") or {}
            device_token = str(response.get("device_token") or "")
            if not isinstance(config, dict) or not device_token:
                log.error("auth self-repair: pairing response missing config/token")
                return
            write_env_values(self.env_path, config_to_env(config, device_token))
            self._apply_settings(Settings.from_env_file(self.env_path))
            # Erfolgreich - der Zaehler beginnt von vorn, sonst wuerde eine
            # Anlage nach ein paar echten Ausfaellen ueber Wochen aufgeben.
            self._auth_repairs = 0
            self._auth_repair_gemeldet = False
            log.warning(
                "auth self-repair: re-paired and refreshed the device token after an upload auth failure"
            )
        except Exception as exc:
            log.error("auth self-repair failed: %s", exc)

    def _refresh_config_if_due(self) -> None:
        """Pull the dashboard config and apply changes live (shadow mode, upload
        mode, folder paths, ...) so edits in the Staff Dashboard reach a running
        PC without re-running the installer or re-pairing."""
        if not self.env_path or self.settings.config_refresh_seconds <= 0:
            return
        if not self.settings.device_token:
            return
        now = time.time()
        if now - self._last_config_refresh < self.settings.config_refresh_seconds:
            return
        self._last_config_refresh = now

        try:
            response = self.client.fetch_config()
        except Exception as exc:
            log.warning("config refresh failed: %s", exc)
            return

        config = response.get("config")
        if not isinstance(config, dict):
            return
        device_token = str(response.get("device_token") or self.settings.device_token)
        desired = config_to_env(config, device_token)

        current = load_env_file(self.env_path)
        changed = {key: value for key, value in desired.items() if current.get(key) != value}
        if not changed:
            return

        log.info("applying dashboard config changes: %s", ", ".join(sorted(changed)))
        write_env_values(self.env_path, desired)
        new_settings = Settings.from_env_file(self.env_path)
        self._apply_settings(new_settings)

    def _apply_settings(self, new_settings: Settings) -> None:
        was_shadow = self.settings.shadow_mode
        # Re-read the viewer's recipe too: a dashboard change must not quietly
        # reintroduce a customer number that disagrees with the printed QR.
        self.settings = new_settings.with_viewer_recipe()
        self.settings.ensure_dirs()
        self._build_workers()
        if was_shadow and not new_settings.shadow_mode:
            released = self.store.requeue_shadowed()
            if released:
                log.info("shadow mode turned off: re-queued %s held photos for upload", released)

    def run_once(self) -> dict[str, object]:
        ride_result = self.ride_tracker.scan_once()
        asset_result = self._asset_sync_if_due()
        result = self.scanner.scan_once()
        uploaded = self.uploader.upload_due()
        if uploaded > 0:
            self._last_upload_ok = time.time()
        if self.uploader.auth_failed:
            # Uploads are being rejected on auth -> our device token is stale.
            # Heal it (re-pair) so uploads resume without any manual step.
            self._repair_auth()
        counts = self.store.counts()
        ride_counts = self.store.ride_counts()
        log.info(
            "rides seen=%s new=%s assets=%s queued=%s staged=%s unstable=%s unknown=%s uploaded=%s counts=%s ride_counts=%s",
            ride_result.seen,
            ride_result.new,
            asset_result,
            result.queued,
            result.staged,
            result.skipped_unstable,
            result.skipped_unknown,
            uploaded,
            counts,
            ride_counts,
        )
        self._heartbeat_if_due(counts)
        return {
            "rides_seen": ride_result.seen,
            "rides_new": ride_result.new,
            "asset_sync": asset_result,
            "queued": result.queued,
            "staged": result.staged,
            "skipped_unstable": result.skipped_unstable,
            "skipped_unknown": result.skipped_unknown,
            "uploaded": uploaded,
            "counts": counts,
            "ride_counts": ride_counts,
        }

    def health(self) -> dict[str, object]:
        usage = shutil.disk_usage(self.settings.app_dir.anchor or ".")
        local_status = read_local_status(
            self.settings.statistic_file,
            self.settings.print_count_file,
            paper_capacity=self.settings.paper_capacity,
            paper_warn_remaining=self.settings.paper_warn_remaining,
        )
        operational_status = read_operational_status(self.settings)
        self._note_new_faults(operational_status)

        # Measured facts about the machine, next to what its logs claim. Cached
        # between heartbeats: the probes shell out to Windows and are far too
        # expensive for the two-second main loop.
        probes = self._probes_if_due()
        # `_offline_since is None` heisst: der letzte Heartbeat kam durch, wir
        # haben also gerade eine Verbindung. Das ist der beste verfuegbare
        # Beweis - besser als jede Zeile aus einem Protokoll von heute Nacht.
        devices = _reconcile(
            operational_status.devices, probes, online=self._offline_since is None,
        )
        ride_rollups = self.store.ride_rollups(
            park_id=self.settings.park_id,
            park_slug=self.settings.park_slug,
            machine_id=self.settings.machine_id,
            default_camera_code=self.settings.camera_code,
            days=self.settings.ride_rollup_days,
        )
        today = datetime.now().date().isoformat()
        today_rollups = [item for item in ride_rollups if item.get("business_date") == today]
        photos_taken_today = sum(int(item.get("photos_taken_count") or 0) for item in today_rollups)
        photos_sold_today = sum(int(item.get("photos_sold_count") or 0) for item in today_rollups)
        rides_total = self.store.rides_total()
        photos_sold_total = self.store.photos_sold_total()
        return {
            "app_name": self.settings.app_name,
            "park_slug": self.settings.park_slug,
            "park_id": self.settings.park_id,
            "machine_id": self.settings.machine_id,
            "camera_code": self.settings.camera_code,
            "shadow_mode": self.settings.shadow_mode,
            "state_db": str(self.settings.state_db),
            "log_dir": str(self.settings.log_dir),
            "counts": self.store.counts(),
            "ride_counts": self.store.ride_counts(),
            "asset_sync_enabled": self.settings.asset_sync_enabled,
            "asset_counts": self.store.asset_counts(),
            "operational_devices": devices,
            "operational_events": operational_status.events,
            # Lets the dashboard distinguish "everything is fine" from "we have
            # not been told anything yet" - the old page could not.
            "probes": probes,
            # Was sich von hier aus neu starten laesst. Der Automat sagt es
            # selbst, statt dass das Dashboard raet: nur so kann dort ein Knopf
            # stehen, der auch wirklich etwas bewirkt. Ein PC ohne die noetige
            # Konfiguration meldet eine leere Liste und bekommt keine Knoepfe.
            "restartable": [
                {
                    "key": p.key, "name": p.name, "tech": p.tech,
                    "folge": p.folge, "exe": str(p.exe),
                }
                for p in restartable_programs(self.settings)
            ],
            # Wie lange es laengstens dauert, bis ein Auftrag hier ankommt, und
            # wann die Ruhezeit fuer "heute Nacht" beginnt. Das Dashboard soll
            # den Fortschritt an echten Zahlen messen statt an einer geratenen
            # Sekundenzahl.
            **self._payments_if_due(),
            # Kann dieser Automat ein Testfoto ausloesen? Wie bei den Neustarts
            # sagt er es selbst, damit im Dashboard kein Knopf steht, der ins
            # Leere greift.
            "can_test_photo": (
                self.settings.test_photo_exe is not None
                and self.settings.test_photo_exe.exists()
                and not laeuft_ohne_bildschirm()
            ),
            # Laeuft der Agent als Systemdienst ohne Bildschirmzugriff? Dann
            # gibt es keine Neustart- und Testfoto-Knoepfe, und das Dashboard
            # sagt auch warum - statt sie wortlos verschwinden zu lassen.
            "session_zero": laeuft_ohne_bildschirm(),
            # Die Kundennummer, die dieser Automat WIRKLICH in die Dateinamen
            # schreibt - nach `with_viewer_recipe()`, also die des
            # Verkaufsprogramms. Der Server prueft damit, ob sie fuer diesen
            # Park registriert ist.
            #
            # Am 15.08.2026 war sie es nicht: der Automat schrieb 1234, in
            # `park_cameras` stand nur 7623, und die Fotos landeten bei einem
            # fremden Park. Das war vorher nirgends sichtbar.
            "customer_code": self.settings.customer_code,
            "restart_poll_seconds": self._asset_poll_seconds(),
            "night_window": [
                self.settings.viewer_night_start, self.settings.viewer_night_end,
            ],
            "monitored_sources": len(operational_status.devices) + len(probes),
            "faults_now": sum(1 for d in operational_status.devices if d.status == "down"),
            "warnings_now": sum(1 for d in operational_status.devices if d.status == "degraded"),
            "pending_health_events": self.store.pending_health_event_count(),
            "agent_version": __version__,
            "coin_status": operational_status.coin_status,
            "terminal_status": operational_status.terminal_status,
            "printer_status": operational_status.printer_status,
            "ride_rollups": ride_rollups,
            "photos_taken_today": photos_taken_today,
            "photos_sold_today": photos_sold_today,
            "photo_conversion_today": round(photos_sold_today / photos_taken_today, 4) if photos_taken_today else None,
            "rides_total": rides_total,
            "photos_sold_total": photos_sold_total,
            "photo_conversion_total": round(photos_sold_total / rides_total, 4) if rides_total else None,
            "disk_free_mb": int(usage.free / 1024 / 1024),
            "camera_status": operational_status.camera_status,
            "paper_printed": local_status.paper_printed,
            "paper_capacity": local_status.paper_capacity,
            "paper_remaining": local_status.paper_remaining,
            "paper_status": local_status.paper_status,
            "statistic_file_size": local_status.statistic_file_size,
            "statistic_last_line": local_status.statistic_last_line,
        }

    def _payments_if_due(self) -> dict:
        """Bargeld, Karte und die Wechselgeld-Kontrolle.

        Wie die Messungen im Heartbeat-Takt und nicht im Zwei-Sekunden-Takt der
        Hauptschleife: die NRI-Protokolle sind gross, und der Bestand aendert
        sich ohnehin nur zweimal am Tag.
        """
        if time.time() - self._last_payment_scan < self.settings.heartbeat_seconds:
            return self._payment_cache
        self._last_payment_scan = time.time()

        try:
            self._payment_cache = read_payments(self.settings)
            self._melde_geldprobleme(self._payment_cache)
        except Exception as exc:  # darf den Heartbeat nie kosten
            log.warning("payment scan failed: %s", exc)
        return self._payment_cache

    def _handle_test_photo(self, request_id: str, mode: str) -> None:
        """Ein vom Dashboard beauftragtes Testfoto ausloesen.

        Ein Testfoto nachts auszuloesen ergibt keinen Sinn - wer es beauftragt,
        will jetzt wissen, ob die Kette laeuft. `tonight` wird deshalb wie
        `now` behandelt und nicht aufgeschoben.
        """
        if self.settings.test_photo_exe is None:
            log.info("test photo ordered but not configured on this PC")
            self._pending_restart_ack = request_id or "rejected"
            self.store.record_health_event(
                kind="camera", severity="warning",
                summary="Testfoto nicht möglich: auf diesem Automaten nicht eingerichtet",
                detail=f"Auftrag {request_id}",
            )
            return

        # Genau einmal auslösen. Ohne diesen Anspruch würden zwei Agenten den
        # Auftrag im selben Fenster abholen und die Kamera zweimal auslösen.
        if not self.store.auftrag_beanspruchen(request_id):
            log.info(
                "test photo order '%s' was already carried out - acknowledging only",
                request_id,
            )
            self._pending_restart_ack = request_id or "done"
            return

        log.warning("triggering test photo on dashboard order '%s' (mode=%s)",
                    request_id, mode)
        ergebnis = trigger_test_photo(self.settings)
        self._pending_restart_ack = request_id or "done"

        meldung = ergebnis.reason
        schwere = "info" if ergebnis.performed else "error"

        # Das Bild liegt roh in `fotos\` - die Lichtschranken-Software stempelt
        # es nicht, weil sie es nicht ausgeloest hat. Also selbst hochladen,
        # als Testfoto gekennzeichnet, damit es sichtbar wird ohne im Umsatz zu
        # erscheinen.
        if ergebnis.performed:
            try:
                bild = _juengstes_bild(self.settings.raw_dir)
                if bild is None:
                    meldung += " (kein Bild zum Hochladen gefunden)"
                else:
                    pfad = lade_testfoto_hoch(self.settings, self.client, bild)
                    meldung += f" und hochgeladen ({Path(pfad).name})"
            except NichtZuordenbar as exc:
                # Die Bremse hat gegriffen. Bewusst als Fehler melden: lieber
                # kein Testfoto als eines im falschen Park.
                schwere = "error"
                meldung += f" - NICHT hochgeladen: {exc}"
                log.error("test photo upload refused: %s", exc)
            except Exception as exc:
                schwere = "warning"
                meldung += f" - Upload fehlgeschlagen: {exc}"
                log.exception("test photo upload failed")

        self.store.record_health_event(
            kind="camera",
            severity=schwere,
            summary=(
                f"Testfoto: {meldung}" if ergebnis.performed
                else f"Testfoto fehlgeschlagen: {meldung}"
            ),
            detail=f"Vom Dashboard beauftragt (Auftrag {request_id})",
        )

    def _melde_geldprobleme(self, daten: dict) -> None:
        """Auffaellige Zahlungen und leere Roehren in den Verlauf schreiben.

        Der Anlass: ein defekter Muenzwechsler gab ueber lange Zeit zu viel
        Wechselgeld heraus, ohne dass es jemand bemerkte. Eine Abweichung
        einmal zu melden ist genau das, was damals gefehlt hat - sie bei jedem
        Heartbeat zu wiederholen waere dagegen Laerm, deshalb der Merker.
        """
        for befund in (daten.get("payments") or {}).get("auffaellig", []):
            kennung = f"{befund['zeit']}|{befund['abweichung_cent']}"
            if kennung in self._gemeldete_zahlungen:
                continue
            self._gemeldete_zahlungen.add(kennung)

            abweichung = befund["abweichung_cent"] / 100
            zu_viel = befund["abweichung_cent"] > 0
            self.store.record_health_event(
                kind="cash",
                # Zu viel heraus ist ein Verlust, der sich mit jedem Verkauf
                # wiederholt - das ist ein Fehler, keine Warnung.
                severity="error" if zu_viel else "warning",
                summary=(
                    f"Wechselgeld stimmt nicht: {abs(abweichung):.2f} € "
                    f"{'zu viel' if zu_viel else 'zu wenig'} ausgezahlt"
                ),
                detail=(
                    f"Verkauf {befund['zeit']}, Preis "
                    f"{befund['betrag_cent'] / 100:.2f} €, eingeworfen "
                    f"{befund['eingeworfen_cent'] / 100:.2f} €, erwartet "
                    f"{befund['erwartetes_wechselgeld_cent'] / 100:.2f} €, "
                    f"ausgezahlt {befund['ausgezahlt_cent'] / 100:.2f} €"
                ),
            )

        for warnung in daten.get("coin_warnings", []):
            kennung = f"bestand|{warnung['cent']}|{warnung['stufe']}"
            if kennung in self._gemeldete_zahlungen:
                continue
            self._gemeldete_zahlungen.add(kennung)
            self.store.record_health_event(
                kind="cash",
                severity="warning" if warnung["stufe"] == "leer" else "info",
                summary=f"Wechselgeld: {warnung['text']}",
                detail="Nachfüllen, sonst bekommen Gäste zu wenig zurück.",
            )

    def _probes_if_due(self) -> list[dict]:
        """Measured machine facts, refreshed at most once per heartbeat.

        The probes start PowerShell and open a socket, so they cost far more
        than a log read. Running them on every loop pass would put a constant
        load on a kiosk PC that has better things to do.
        """
        if not self.settings.probe_enabled:
            return []
        now = time.time()
        if self._probe_cache is not None and (now - self._last_probe) < self.settings.heartbeat_seconds:
            return self._probe_cache

        self._last_probe = now
        try:
            self._probe_cache = collect_probes(self.settings)
        except Exception as exc:
            log.warning("machine probes failed: %s", exc)
            self._probe_cache = self._probe_cache or []
        return self._probe_cache

    def _note_new_faults(self, status) -> None:
        """Buffer a note the first time a tool reports a fault.

        The heartbeat only ever carried the *current* picture, so a fault that
        appeared and cleared between two beats left no trace at all. Recording
        it here means the dashboard can show when something broke and what it
        said - not merely that it is broken right now.

        Keyed by tool plus message, so a standing fault is noted once while a
        genuinely new message is noted again.
        """
        for device in status.devices:
            if device.severity not in ("error", "warning"):
                continue
            fingerprint = f"{device.name}|{device.detail[:120]}"
            if fingerprint in self._reported_faults:
                continue
            self._reported_faults.add(fingerprint)
            self.store.record_health_event(
                kind=device.kind,
                severity=device.severity,
                summary=f"{device.name}: {'Stoerung' if device.severity == 'error' else 'Warnung'}",
                detail=device.detail,
                occurred_at=device.last_seen_at,
            )
            # RELAY_MARKER lets the monitor filter this line back out when it
            # reads our own log - otherwise relaying a warning would itself look
            # like a new warning on the next scan.
            log.warning("%s %s meldet: %s", RELAY_MARKER, device.name, device.detail[:180])

        # Bound the memory: a long-running agent must not accumulate for ever.
        if len(self._reported_faults) > 500:
            self._reported_faults.clear()

    def _heartbeat_if_due(self, counts: dict[str, int]) -> None:
        now = time.time()
        if now - self._last_heartbeat < self.settings.heartbeat_seconds:
            return
        self._last_heartbeat = now
        payload = self.health()
        payload["queue_count"] = counts.get("queued", 0) + counts.get("retry", 0)

        # Everything noted while the server was unreachable rides along on the
        # first heartbeat that gets through - that is the whole point of the
        # buffer, so an outage explains itself afterwards instead of vanishing.
        buffered = self.store.undelivered_health_events()
        if buffered:
            payload["buffered_events"] = buffered

        try:
            self.client.status(payload)
            self._last_heartbeat_ok = now
            if buffered:
                self.store.mark_health_events_delivered([int(item["id"]) for item in buffered])
                log.info("delivered %s buffered health notes after reconnect", len(buffered))
            if self._offline_since is not None:
                outage_minutes = (now - self._offline_since) / 60.0
                log.warning(
                    "connection restored after %.1f minutes offline (reason: %s)",
                    outage_minutes,
                    self._offline_reason or "unknown",
                )
                self.store.record_health_event(
                    kind="connection",
                    severity="warning",
                    summary=f"Verbindung nach {outage_minutes:.0f} Minuten wiederhergestellt",
                    detail=f"Ursache des Ausfalls: {self._offline_reason or 'unbekannt'}",
                )
                self._offline_since = None
                self._offline_reason = None
                self.store.set_app_state("offline_since", None)
                self.store.set_app_state("offline_reason", None)
        except Exception as exc:
            # Loud on purpose: a silent heartbeat failure is exactly the class
            # of bug that hid the connection dropping for hours. ERROR so it
            # shows up in the log's error filter next time.
            log.error("heartbeat failed (server NOT updated): %s", exc)
            if self._offline_since is None:
                # First miss of this outage - note when and why, once. Repeating
                # it every minute would bury the useful entry.
                self._offline_since = now
                self._offline_reason = str(exc)[:400]
                # Survives a restart, so the reconnect can still state the real
                # duration instead of starting the clock over.
                self.store.set_app_state("offline_since", str(now))
                self.store.set_app_state("offline_reason", self._offline_reason)
                self.store.record_health_event(
                    kind="connection",
                    severity="error",
                    summary="Verbindung zum Server verloren",
                    detail=str(exc)[:2000],
                )

    def _asset_poll_seconds(self) -> float:
        """Wie oft der Asset-Abruf laeuft.

        Sobald Neustarts freigeschaltet sind, haengt an diesem Abruf auch der
        Neustart-Auftrag - dann zaehlt, wie lange ein Betreiber nach dem Klick
        wartet, nicht wie oft sich Bilder aendern.
        """
        if self.settings.viewer_restart_enabled:
            return min(self.settings.asset_sync_seconds,
                       self.settings.restart_poll_seconds)
        return self.settings.asset_sync_seconds

    def _asset_sync_if_due(self) -> dict[str, int] | None:
        if not self.settings.asset_sync_enabled:
            return None
        now = time.time()
        if now - self._last_asset_sync < self._asset_poll_seconds():
            return None
        self._last_asset_sync = now

        if self.settings.shadow_mode:
            log.info("asset sync is enabled while upload shadow mode is active")

        try:
            # Any restart carried out since the last poll is acknowledged with
            # this call, so the server can clear the order.
            ack = self._pending_restart_ack
            result = self.asset_sync.sync_once(restart_ack=ack)
            if ack:
                self._pending_restart_ack = None

            self._handle_restart_request(result)

            return {
                "fetched": result.fetched,
                "applied": result.applied,
                "skipped": result.skipped,
                "failed": result.failed,
            }
        except Exception as exc:
            log.warning("asset sync failed: %s", exc)
            return {"fetched": 0, "applied": 0, "skipped": 0, "failed": 1}

    def _handle_restart_request(self, result) -> None:
        """Carry out a dashboard-ordered restart when it is due.

        `now` runs at the next poll; `tonight` waits for the quiet window so a
        restart never interrupts a sale. After a successful viewer restart the
        assets that were blocked by the open file handle are picked up on the
        very next poll, which is why nothing else needs to be re-triggered here.

        Das Ziel kommt als Schluessel vom Server ("viewer", "camera", ...) und
        wird von `find_program` gegen die Konfiguration DIESES PCs aufgeloest.
        Ein unbekannter Schluessel wird abgelehnt und quittiert - sonst bliebe
        der Auftrag fuer immer offen und wuerde bei jedem Abruf neu versucht.
        """
        request = result.restart_request
        if not isinstance(request, dict):
            return
        if not self.settings.viewer_restart_enabled:
            log.info("restart order received but restarting is not enabled on this PC")
            return

        request_id = str(request.get("id") or request.get("requested_at") or "")
        mode = str(request.get("mode") or "now").strip().lower()
        target = str(request.get("target") or "viewer").strip().lower()

        # Ein liegengebliebener Auftrag darf nicht nachtraeglich losgehen.
        #
        # Auftraege bleiben in den Einstellungen stehen, bis sie quittiert sind.
        # Ein frisch aktualisierter Automat wuerde sonst beim ersten Abruf einen
        # Neustart ausfuehren, den vor Stunden jemand angestossen und laengst
        # vergessen hat - genau die Sorte "es macht von selbst etwas", die auf
        # einer laufenden Anlage nichts zu suchen hat.
        #
        # `tonight` ist ausgenommen: der Auftrag SOLL bis zur Ruhezeit warten.
        if mode != "tonight":
            alter = _auftragsalter_minuten(request)
            if alter is not None and alter > AUFTRAG_MAX_ALTER_MINUTEN:
                log.warning(
                    "discarding restart order '%s': %.0f minutes old, limit is %d",
                    request_id, alter, AUFTRAG_MAX_ALTER_MINUTEN,
                )
                self._pending_restart_ack = request_id or "expired"
                self.store.record_health_event(
                    kind="restart", severity="info",
                    summary="Alter Neustart-Auftrag verworfen",
                    detail=(
                        f"Der Auftrag war {alter:.0f} Minuten alt (Grenze "
                        f"{AUFTRAG_MAX_ALTER_MINUTEN}). Bitte bei Bedarf neu auslösen."
                    ),
                )
                return

        # Ein Testfoto ist kein Neustart - es haelt nichts an, es loest nur aus.
        # Es reist ueber denselben Auftragsweg, weil der bereits abgesichert und
        # quittiert ist; behandelt wird es aber getrennt.
        if target == "testphoto":
            self._handle_test_photo(request_id, mode)
            return

        if find_program(self.settings, target) is None:
            log.error(
                "restart order '%s' names target '%s', which this PC does not "
                "have configured - rejecting", request_id, target,
            )
            self._pending_restart_ack = request_id or "rejected"
            self.store.record_health_event(
                kind="restart",
                severity="warning",
                summary=f"Neustart-Auftrag abgelehnt: {target} ist hier nicht eingerichtet",
                detail=f"Auftrag {request_id}",
            )
            return

        if mode == "tonight" and not in_night_window(self.settings):
            log.info(
                "restart order '%s' is scheduled for the quiet window (%s-%s), waiting",
                request_id,
                self.settings.viewer_night_start,
                self.settings.viewer_night_end,
            )
            return

        # Ab hier wird wirklich etwas angehalten. Der Anspruch steht deshalb
        # genau hier und nicht weiter oben: ein `tonight`-Auftrag durchlaeuft
        # die Pruefungen oben stundenlang, ohne ausgefuehrt zu werden - wuerde
        # er dabei beansprucht, ginge er nachts nie los.
        if not self.store.auftrag_beanspruchen(request_id):
            log.info(
                "restart order '%s' was already carried out - acknowledging only",
                request_id,
            )
            self._pending_restart_ack = request_id or "done"
            return

        log.warning(
            "carrying out dashboard restart order '%s' (target=%s, mode=%s)",
            request_id, target, mode,
        )
        outcome = restart_program(self.settings, target)
        if outcome.performed:
            log.warning("%s on dashboard order '%s'", outcome.reason, request_id)
            self.store.record_health_event(
                kind="restart", severity="info",
                summary=outcome.reason,
                detail=f"Vom Dashboard beauftragt ({mode})",
            )
            # Acknowledged on the next poll; the order stays open until then, so
            # a crash between restart and ack simply repeats the restart rather
            # than silently dropping it.
            self._pending_restart_ack = request_id or "done"
        else:
            log.error("restart order '%s' could not be carried out: %s", request_id, outcome.reason)
            # Auch der Fehlschlag gehoert in den Verlauf: keines dieser
            # Programme steht im Autostart, ein "nicht hochgekommen" heisst also,
            # dass jemand hinsehen muss.
            self.store.record_health_event(
                kind="restart", severity="error",
                summary=f"Neustart fehlgeschlagen: {outcome.reason}",
                detail=f"Auftrag {request_id}, Ziel {target}",
            )
            self._pending_restart_ack = request_id or "failed"
