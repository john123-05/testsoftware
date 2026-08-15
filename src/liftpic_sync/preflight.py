"""Vor dem Umschalten nachsehen, ohne irgendetwas zu verändern.

Wozu
----
Ein Update auf einer laufenden Anlage ist der gefährlichste Moment. Genau dann
will man wissen, was der Agent auf DIESEM PC vorfinden wird - bevor er es tut:

* Welche Kundennummer würde gelten? Weicht sie von der des Verkaufsprogramms ab?
* Läuft der Agent mit Bildschirmzugriff, oder wären Neustarts schädlich?
* Welche Programme und Protokolle existieren wirklich?
* Welche Merkmale würden sich einschalten - und welche stumm bleiben?

Alles hier ist **rein lesend**. Der Befehl legt nichts an, ändert nichts und
lädt nichts hoch. Er darf jederzeit auf einer produktiven Anlage laufen.
"""
from __future__ import annotations

from pathlib import Path

from .config import Settings
from .viewer_control import laeuft_ohne_bildschirm, restartable_programs
from .viewer_settings import read_viewer_prices, read_viewer_recipe


def _da(pfad: Path | None) -> str:
    if pfad is None:
        return "nicht eingerichtet"
    return "vorhanden" if Path(pfad).exists() else "FEHLT"


def _alter(pfad: Path | None) -> str:
    """Wie frisch eine Datei ist - eine tote Quelle sieht sonst gesund aus."""
    if pfad is None or not Path(pfad).exists():
        return ""
    import time
    stunden = (time.time() - Path(pfad).stat().st_mtime) / 3600
    if stunden < 2:
        return f", zuletzt vor {stunden * 60:.0f} Min. geschrieben"
    if stunden < 72:
        return f", zuletzt vor {stunden:.0f} Std. geschrieben"
    return f", zuletzt vor {stunden / 24:.0f} Tagen geschrieben"


def _treffer(muster: str) -> int:
    import glob
    return len(glob.glob(muster)) if muster else 0


def sammle(settings: Settings) -> list[str]:
    """Den Bericht als Zeilen. Getrennt vom Ausgeben, damit er prüfbar ist."""
    z: list[str] = []
    z.append("=" * 68)
    z.append("  LIFTPIC-SYNC PREFLIGHT - es wird nichts verändert")
    z.append("=" * 68)

    z.append("")
    z.append("ZUORDNUNG")
    z.append(f"  Park:              {settings.park_slug}  ({settings.park_id})")
    z.append(f"  Automat:           {settings.machine_id}")
    z.append(f"  Kundennummer:      {settings.customer_code}")
    z.append(f"  Code-Stellen:      {settings.file_code_positions}")

    recipe = read_viewer_recipe(settings.viewer_settings_xml)
    if recipe is None:
        z.append("  Verkaufsprogramm:  Settings.xml nicht lesbar - "
                 "die Kundennummer oben gilt")
    else:
        gleich = recipe.customer_number == settings.customer_code
        z.append(f"  Settings.xml sagt: {recipe.customer_number or '(keine)'}"
                 f"  {'stimmt überein' if gleich else 'ABWEICHUNG'}")
        if not gleich:
            if settings.viewer_recipe_enabled:
                z.append("      -> VIEWER_RECIPE_ENABLED ist AN: der Agent würde "
                         f"auf {recipe.customer_number} umstellen.")
                z.append("      -> Prüfen, ob diese Nummer für den Park registriert "
                         "ist. Sonst landen Fotos im falschen Park.")
            else:
                z.append(f"      -> Übernahme ist AUS: es bleibt bei "
                         f"{settings.customer_code}. Gedruckter und hochgeladener "
                         "Code weichen dann voneinander ab.")

    z.append("")
    z.append("BILDSCHIRMZUGRIFF")
    if laeuft_ohne_bildschirm():
        z.append("  Sitzung 0 (Systemdienst) - KEIN Zugriff auf den Bildschirm.")
        z.append("  Neustart- und Testfoto-Knöpfe bleiben ausgeblendet: ein von")
        z.append("  hier gestartetes Programm wäre für den Gast unsichtbar.")
    else:
        z.append("  Benutzersitzung - Neustarts sind möglich und sichtbar.")

    z.append("")
    z.append("ORDNER UND DATEIEN")
    for name, pfad in (
        ("Rohbilder (RAW_DIR)", settings.raw_dir),
        ("Verarbeitet", settings.processed_dir),
        ("QR-Ausgabe", settings.qrcode_dir),
        ("Statistik", settings.statistic_file),
        ("Druckzähler", settings.print_count_file),
        ("Settings.xml", settings.viewer_settings_xml),
        ("Münzbestand", settings.coin_stats_file),
    ):
        z.append(f"  {name:22} {_da(pfad)}{_alter(pfad)}")

    z.append("")
    z.append("PROGRAMME (für Neustart und Testfoto)")
    for name, pfad in (
        ("Verkaufsprogramm", settings.viewer_exe),
        ("Kamera-Software", settings.camera_exe),
        ("Lichtschranke", settings.lightbarrier_exe),
        ("Testfoto-Auslöser", settings.test_photo_exe),
    ):
        z.append(f"  {name:22} {_da(pfad)}")

    z.append("")
    z.append("PROTOKOLLE")
    z.append(f"  Betriebsprotokolle:  {sum(_treffer(m) for m in settings.operational_log_globs)} Dateien")
    z.append(f"  Münzprotokolle:      {_treffer(settings.coin_log_glob)} Dateien")
    z.append(f"  Kartenprotokolle:    {_treffer(settings.card_log_glob)} Dateien")

    z.append("")
    z.append("WAS SICH EINSCHALTEN WÜRDE")
    programme = restartable_programs(settings)
    z.append(f"  Neustart-Knöpfe:     "
             f"{', '.join(p.name for p in programme) if programme else 'keine'}")
    z.append(f"  Testfoto:            "
             f"{'ja' if settings.test_photo_exe and Path(settings.test_photo_exe).exists() and not laeuft_ohne_bildschirm() else 'nein'}")
    z.append(f"  Münzbestand:         {'ja' if settings.coin_stats_file else 'nein'}")
    z.append(f"  Zahlungsauswertung:  "
             f"{'ja' if (settings.coin_log_glob or settings.card_log_glob) else 'nein'}"
             f" (Zeitraum {settings.payment_days} Tage)")
    preise = read_viewer_prices(settings.viewer_settings_xml)
    z.append(f"  Erkannte Preise:     "
             f"{', '.join(f'{c / 100:.2f} EUR' for c in preise) if preise else 'keine'}")
    z.append(f"  Upload-Quelle:       {settings.upload_source}")
    z.append(f"  Schattenbetrieb:     {'JA - es wird nichts hochgeladen' if settings.shadow_mode else 'nein'}")

    z.append("")
    z.append("=" * 68)
    return z


def bericht(settings: Settings) -> str:
    return "\n".join(sammle(settings))
