from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .envfile import load_env_file, parse_bool


def _get(values: dict[str, str], key: str, default: str = "") -> str:
    env_value = os.environ.get(key)
    if env_value:
        return env_value
    return values.get(key, default)


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
    camera_code: str = "default"
    config_refresh_seconds: float = 120
    # If no heartbeat reaches the server for this many seconds the process
    # exits(1) so the Windows scheduled task's restart-on-failure recovers it
    # with a fresh process. 0 disables the watchdog. Must exceed
    # heartbeat_seconds by a comfortable margin.
    watchdog_seconds: float = 600
    # If uploads keep getting rejected on auth (a stale/empty device token), the
    # agent re-pairs itself with this stored pairing code to fetch a fresh token
    # - self-heals the recurring "uploads rejected 401" outage, no manual step.
    pairing_code: str = ""
    # Exit(1) for a clean restart if there is fresh queued upload work but no
    # upload has succeeded for this long (0 disables). Complements
    # watchdog_seconds, which only covers a dead heartbeat, not a dead upload.
    upload_stall_seconds: float = 900
    paper_capacity: int = 0
    paper_warn_remaining: int = 20
    ride_count_enabled: bool = True
    ride_count_source: str = "processed,raw"
    ride_rollup_days: int = 14
    # Which 1-based digit positions of the camera capture number form the
    # picture code - must equal jpeg4web's CodePositionsInFilename (Imst: 2,3,4,5)
    # so our computed claim code matches the printed QR.
    file_code_positions: str = "2,3,4,5"
    asset_sync_enabled: bool = False
    asset_sync_seconds: float = 300
    asset_backup_dir: Path | None = None
    asset_allowed_roots: tuple[Path, ...] = ()
    # Restarting the kiosk viewer. Needed because the viewer reads files like
    # hintergrund.png once at startup and holds the handle open, so a newly
    # synced asset only becomes visible after a restart. Off unless an exe is
    # configured, so a PC without this setting behaves exactly as before.
    viewer_exe: Path | None = None
    viewer_restart_enabled: bool = False
    # Weitere Programme, die sich vom Dashboard aus neu starten lassen. Jedes
    # ist einzeln zu hinterlegen und bleibt ohne Eintrag abgeschaltet - der
    # Server kann also nie einen Pfad vorgeben, sondern nur einen Schluessel
    # nennen, den dieser PC selbst kennt.
    #
    # Nicht dabei und mit Absicht:
    #   * der Uploader selbst - nichts wuerde ihn wieder starten, danach waere
    #     der Automat blind und ohne Fernzugriff;
    #   * die Druckerwarteschlange - dafuer braeuchte der Agent
    #     Administratorrechte, die er nicht hat;
    #   * Muenzpruefer und Kartenterminal - Geraete, keine Programme.
    camera_exe: Path | None = None
    lightbarrier_exe: Path | None = None
    # Das Programm, mit dem die Lichtschranke eine Aufnahme ausloest. Steht in
    # AidaTest.ini als `Executable=`. Dasselbe von Hand aufzurufen ergibt ein
    # Testfoto, das denselben Weg nimmt wie ein echtes.
    test_photo_exe: Path | None = None
    # Wie oft nach einem Neustart-Auftrag gefragt wird, solange Neustarts
    # freigeschaltet sind.
    #
    # Der Auftrag reist mit dem Asset-Abruf mit, und der lief bisher nur alle
    # `asset_sync_seconds` (voreingestellt 300). "Jetzt neu starten" konnte
    # damit fuenf Minuten liegen bleiben, waehrend das Dashboard einen
    # 45-Sekunden-Balken zeigte. Der Abruf selbst ist billig - eine Anfrage und
    # ein Hash-Vergleich ueber drei kleine Dateien -, deshalb darf er haeufiger
    # laufen, sobald ueberhaupt jemand einen Neustart ausloesen kann.
    restart_poll_seconds: float = 20.0
    # Bargeld und Karte. Alles optional: fehlt eine Quelle, entfaellt der
    # jeweilige Teil der Auswertung, statt dass etwas geraten wird.
    coin_stats_file: Path | None = None
    coin_log_glob: str = ""
    card_log_glob: str = ""
    # Ab wann eine Muenzsorte als knapp gilt. Null Stueck heisst immer "leer".
    coin_low_count: int = 10
    # Wie viele Tage zurueck Zahlungen ausgewertet werden. Die NRI-Protokolle
    # reichen Jahre zurueck; alles davon bei jedem Heartbeat zu lesen waere
    # Verschwendung, und aelter als ein paar Tage interessiert niemanden mehr.
    payment_days: int = 7
    # Quiet window for scheduled ("tonight") restarts, local time. A restart
    # request marked `tonight` waits until the kiosk is closed instead of
    # interrupting a sale.
    viewer_night_start: str = "23:30"
    viewer_night_end: str = "05:00"
    # The viewer's own config file. When set, the customer number and the
    # picture-code positions are taken FROM IT instead of from the values below,
    # because the viewer is what prints the QR code. Two independent copies of
    # that recipe are exactly how a printed code and an uploaded code drift
    # apart. Empty disables it and the .env values stand.
    viewer_settings_xml: Path | None = None
    # Darf die Code-Vorschrift des Verkaufsprogramms die konfigurierte
    # ueberschreiben? **Vorgabe: nein.**
    #
    # Am 15.08.2026 hat genau das Schaden angerichtet: der Automat uebernahm die
    # Kundennummer 1234 aus der Settings.xml, registriert war aber 7623 - und
    # weil der Server den Park aus dieser Nummer ableitet, landete der Upload
    # beim falschen Kunden. Eine Aktualisierung darf die Vorschrift einer
    # laufenden Anlage niemals im Vorbeigehen aendern; die Abweichung wird
    # gemeldet, angewandt wird sie erst nach bewusster Freigabe.
    viewer_recipe_enabled: bool = False
    # Direct measurements of the machine, alongside reading its log files. A
    # crashed program writes nothing at all - its last log line still looks
    # healthy - so "is it running?" has to be asked, not inferred.
    probe_enabled: bool = True
    # Payment terminal, for a plain reachability check (no protocol talk).
    terminal_host: str = ""
    terminal_port: int = 22000
    # Serial ports the light barrier needs. Missing ones mean it cannot trigger.
    expected_com_ports: tuple[str, ...] = ()
    operational_log_globs: tuple[str, ...] = ()
    operational_log_tail_lines: int = 80
    operational_log_stale_minutes: int = 240
    operational_log_defunct_minutes: int = 2880

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
        asset_backup_dir = _get(values, "ASSET_BACKUP_DIR", str(app_dir / "backups" / "assets")).strip()
        allowed_roots_raw = _get(
            values,
            "ASSET_SYNC_ALLOWED_ROOTS",
            r"C:\liftpic\samuel_neu;C:\liftpic\imageloader;C:\liftpic\jpeg4web",
        )
        allowed_roots = tuple(
            Path(item.strip())
            for item in allowed_roots_raw.replace(",", ";").split(";")
            if item.strip()
        )
        default_operational_globs = (
            r"C:\liftpic\imageloader\*.txt;"
            r"C:\liftpic\imageloader\*.log;"
            r"C:\liftpic\kosel\*.log;"
            r"C:\liftpic\CAMware\log\*.txt;"
            r"C:\liftpic\CAMware\*.log;"
            # The live camera log is 3gerlog.txt - named by hand, so "*.log" in
            # that folder only matches leftovers from 2021. Listed explicitly to
            # keep file.txt / path.txt / test.txt out of the evaluation.
            r"C:\liftpic\3GerTis\3gerlog.txt;"
            r"C:\liftpic\3GerTis\*.log"
        )
        viewer_exe_raw = _get(values, "VIEWER_EXE", "").strip()
        camera_exe_raw = _get(values, "CAMERA_EXE", "").strip()
        lightbarrier_exe_raw = _get(values, "LIGHTBARRIER_EXE", "").strip()
        viewer_settings_raw = _get(values, "VIEWER_SETTINGS_XML", "").strip()
        com_ports_raw = _get(values, "EXPECTED_COM_PORTS", "").strip()
        com_ports = tuple(
            item.strip().upper()
            for item in com_ports_raw.replace(";", ",").split(",")
            if item.strip()
        )

        operational_log_globs_raw = _get(values, "OPERATIONAL_LOG_GLOBS", default_operational_globs)
        operational_log_globs = tuple(
            item.strip()
            for item in operational_log_globs_raw.replace(",", ";").split(";")
            if item.strip()
        )

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
            config_refresh_seconds=float(_get(values, "CONFIG_REFRESH_SECONDS", "120")),
            watchdog_seconds=float(_get(values, "WATCHDOG_SECONDS", "600")),
            pairing_code=_get(values, "PAIRING_CODE", "").strip(),
            upload_stall_seconds=float(_get(values, "UPLOAD_STALL_SECONDS", "900")),
            paper_capacity=int(_get(values, "PAPER_CAPACITY", "0") or "0"),
            paper_warn_remaining=int(_get(values, "PAPER_WARN_REMAINING", "20") or "20"),
            archive_raw=parse_bool(_get(values, "ARCHIVE_RAW", "false"), False),
            camera_code=_get(values, "CAMERA_CODE", _get(values, "MACHINE_ID", "default")).strip() or "default",
            ride_count_enabled=parse_bool(_get(values, "RIDE_COUNT_ENABLED", "true"), True),
            ride_count_source=_get(values, "RIDE_COUNT_SOURCE", "processed,raw").strip().lower(),
            ride_rollup_days=int(_get(values, "RIDE_ROLLUP_DAYS", "14")),
            file_code_positions=_get(values, "FILE_CODE_POSITIONS", "2,3,4,5").strip() or "2,3,4,5",
            asset_sync_enabled=parse_bool(_get(values, "ASSET_SYNC_ENABLED", "false"), False),
            asset_sync_seconds=float(_get(values, "ASSET_SYNC_SECONDS", "300")),
            asset_backup_dir=Path(asset_backup_dir) if asset_backup_dir else None,
            asset_allowed_roots=allowed_roots,
            viewer_exe=Path(viewer_exe_raw) if viewer_exe_raw else None,
            camera_exe=Path(camera_exe_raw) if camera_exe_raw else None,
            lightbarrier_exe=Path(lightbarrier_exe_raw) if lightbarrier_exe_raw else None,
            test_photo_exe=(
                Path(test_photo_raw)
                if (test_photo_raw := _get(values, "TEST_PHOTO_EXE", "").strip())
                else None
            ),
            viewer_restart_enabled=parse_bool(_get(values, "VIEWER_RESTART_ENABLED", "false"), False),
            restart_poll_seconds=float(_get(values, "RESTART_POLL_SECONDS", "20") or "20"),
            coin_stats_file=(
                Path(coin_stats_raw) if (coin_stats_raw := _get(values, "COIN_STATS_FILE", "").strip())
                else None
            ),
            coin_log_glob=_get(values, "COIN_LOG_GLOB", "").strip(),
            card_log_glob=_get(values, "CARD_LOG_GLOB", "").strip(),
            coin_low_count=int(_get(values, "COIN_LOW_COUNT", "10") or "10"),
            payment_days=int(_get(values, "PAYMENT_DAYS", "7") or "7"),
            viewer_night_start=_get(values, "VIEWER_NIGHT_START", "23:30").strip() or "23:30",
            viewer_night_end=_get(values, "VIEWER_NIGHT_END", "05:00").strip() or "05:00",
            viewer_settings_xml=Path(viewer_settings_raw) if viewer_settings_raw else None,
            viewer_recipe_enabled=parse_bool(_get(values, "VIEWER_RECIPE_ENABLED", "false"), False),
            probe_enabled=parse_bool(_get(values, "PROBE_ENABLED", "true"), True),
            terminal_host=_get(values, "TERMINAL_HOST", "").strip(),
            terminal_port=int(_get(values, "TERMINAL_PORT", "22000") or "22000"),
            expected_com_ports=com_ports,
            operational_log_globs=operational_log_globs,
            operational_log_tail_lines=int(_get(values, "OPERATIONAL_LOG_TAIL_LINES", "80")),
            operational_log_stale_minutes=int(_get(values, "OPERATIONAL_LOG_STALE_MINUTES", "240")),
            operational_log_defunct_minutes=int(_get(values, "OPERATIONAL_LOG_DEFUNCT_MINUTES", "2880")),
        )

    def with_viewer_recipe(self) -> "Settings":
        """Take customer number and picture-code positions from the viewer.

        The viewer prints the QR code, so its configuration decides what the
        guest actually scans. Where the two disagree, the viewer's value is the
        one the guest holds in their hand.

        **Only applied when `VIEWER_RECIPE_ENABLED` is on, and it is off by
        default.** The reason is what happened on 15.08.2026: the test machine's
        viewer said 1234 while the dashboard had 7623 registered, the agent
        adopted 1234, and the next upload landed in a different customer's park -
        because the park is derived from that very number.

        Adopting it is only safe once the number is registered for the park.
        Until an installation is known to be in that state, the configured value
        stays and the difference is merely reported. A mismatch is logged either
        way: it means every code printed so far used the other value, and that
        is worth seeing.
        """
        from .viewer_settings import read_viewer_recipe

        recipe = read_viewer_recipe(self.viewer_settings_xml)
        if recipe is None or recipe.is_empty():
            return self

        import dataclasses
        import logging

        log = logging.getLogger(__name__)
        changes: dict[str, object] = {}

        if recipe.customer_number and recipe.customer_number != self.customer_code:
            if self.viewer_recipe_enabled:
                log.warning(
                    "customer number differs: viewer says %s, agent had %s - taking the viewer's "
                    "value, because it is what gets printed into the QR code (source: %s)",
                    recipe.customer_number,
                    self.customer_code,
                    recipe.source,
                )
                changes["customer_code"] = recipe.customer_number
            else:
                # Nicht anwenden, aber laut sagen. Wer die Uebernahme will,
                # schaltet sie ein - nachdem die Nummer registriert ist.
                log.warning(
                    "customer number differs: viewer says %s, agent uses %s - NOT adopting it "
                    "(VIEWER_RECIPE_ENABLED is off). Printed codes and uploaded codes will "
                    "disagree until this is resolved (source: %s)",
                    recipe.customer_number,
                    self.customer_code,
                    recipe.source,
                )

        if recipe.code_positions and recipe.code_positions != self.file_code_positions:
            # Falsche Stellen machen den Code unauffindbar, verschieben ihn aber
            # nicht in einen fremden Park. Trotzdem am selben Schalter: eine
            # Aktualisierung darf die Code-Vorschrift einer laufenden Anlage
            # nicht im Vorbeigehen aendern.
            log.warning(
                "picture-code positions differ: viewer says %s, agent has %s - %s (source: %s)",
                recipe.code_positions,
                self.file_code_positions,
                "taking the viewer's value" if self.viewer_recipe_enabled
                else "NOT adopting it (VIEWER_RECIPE_ENABLED is off)",
                recipe.source,
            )
            if self.viewer_recipe_enabled:
                changes["file_code_positions"] = recipe.code_positions

        if not changes:
            log.info("code recipe matches the viewer's configuration")
            return self
        return dataclasses.replace(self, **changes)

    def ensure_dirs(self) -> None:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.state_db.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        if self.asset_backup_dir:
            self.asset_backup_dir.mkdir(parents=True, exist_ok=True)
