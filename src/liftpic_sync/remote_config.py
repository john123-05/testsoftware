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

    werte = {
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
        "PAPER_CAPACITY": str(int(config.get("paper_capacity") or 0)),
        "PAPER_WARN_REMAINING": str(int(config.get("paper_warn_remaining") or 20)),
    }
    werte.update(_merkmale_aus_einstellungen(config))
    return werte


# Merkmale, die sich aus dem Dashboard schalten lassen sollen.
#
# Bis hierher konnte man einen Automaten nur an seiner `.env` umstellen - also
# nur vor Ort. Fuer Imst hiesse das: nach dem Rollout noch einmal hinfahren,
# um Neustart-Knoepfe, Testfoto oder die Muenzauswertung einzuschalten.
#
# Die Zuordnung steht bewusst getrennt von der Tabelle oben, weil hier eine
# andere Regel gilt: fehlt ein Wert, wird der Schluessel NICHT geschrieben.
# Oben gewinnt bei einem leeren Serverwert ein harter Vorgabewert - genau die
# Falle, ueber die eine Anlage mit eigenen Pfaden auf die Standardpfade
# zurueckgesetzt wuerde. Hier bleibt stattdessen stehen, was am Automaten steht.
FERNSCHALTBAR: tuple[tuple[str, str], ...] = (
    ("viewer_restart_enabled", "VIEWER_RESTART_ENABLED"),
    ("viewer_exe", "VIEWER_EXE"),
    ("camera_exe", "CAMERA_EXE"),
    ("lightbarrier_exe", "LIGHTBARRIER_EXE"),
    ("test_photo_exe", "TEST_PHOTO_EXE"),
    ("viewer_settings_xml", "VIEWER_SETTINGS_XML"),
    ("coin_stats_file", "COIN_STATS_FILE"),
    ("coin_log_glob", "COIN_LOG_GLOB"),
    ("card_log_glob", "CARD_LOG_GLOB"),
    ("operational_log_globs", "OPERATIONAL_LOG_GLOBS"),
    ("asset_sync_enabled", "ASSET_SYNC_ENABLED"),
    ("probe_enabled", "PROBE_ENABLED"),
    ("terminal_host", "TERMINAL_HOST"),
)

# Welche davon Schalter sind und deshalb als true/false geschrieben werden.
FERNSCHALTBAR_BOOLEAN = {
    "viewer_restart_enabled", "asset_sync_enabled", "probe_enabled",
}


def _merkmale_aus_einstellungen(config: dict[str, object]) -> dict[str, str]:
    """Die fernschaltbaren Merkmale aus dem `settings`-Feld der Maschine.

    Nur was ausdruecklich dort steht, wird geschrieben. Ein fehlender Eintrag
    laesst den Wert am Automaten unveraendert - er schaltet ihn nicht ab.
    """
    roh = config.get("settings")
    if not isinstance(roh, dict):
        return {}

    ergebnis: dict[str, str] = {}
    for schluessel, env_name in FERNSCHALTBAR:
        if schluessel not in roh:
            continue
        wert = roh[schluessel]
        if wert is None:
            continue
        if schluessel in FERNSCHALTBAR_BOOLEAN:
            ergebnis[env_name] = _bool_env(wert)
        else:
            ergebnis[env_name] = str(wert)
    return ergebnis
