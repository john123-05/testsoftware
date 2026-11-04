"""Liftpictures Station: lokale Statusseite auf dem Automaten-Bildschirm.

Der Agent schreibt bei jedem Herzschlag in `station_dir` (Vorgabe
`C:\\liftpic\\station`):

- `index.html`: die Seite selbst (aus `station_page.PAGE`), nur bei Aenderung.
- `liftpic-logo.png`: das Liftpictures-Logo (eingebettet, kein Download).
- `park-logo`: das Logo des Parks, einmal von `station_logo_url` geladen.
- `status.js`: der aktuelle Stand als `window.__station({...})`.

Die Seite laedt `status.js` alle paar Sekunden neu. Weil alles lokale Dateien
sind (file://), funktioniert sie ohne Internet - genau dann, wenn man sie am
dringendsten braucht. Bleibt `status.js` stehen, erkennt die Seite das selbst
und sagt, dass der PC neu gestartet werden soll.

Geoeffnet wird sie per Verknuepfung (scripts/station_einrichten.ps1):
  msedge --app=file:///C:/liftpic/station/index.html --start-fullscreen
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
import urllib.request
from pathlib import Path

from .station_assets import LIFTPIC_LOGO_PNG_B64, STATION_ICON_ICO_B64
from .station_page import PAGE

log = logging.getLogger(__name__)

LOGO_MAX_BYTES = 3 * 1024 * 1024
LOGO_RETRY_SECONDS = 600
_letzter_versuch: dict[str, float] = {}
LOGO_TYPES = {"image/png", "image/webp", "image/jpeg", "image/svg+xml", "image/gif"}


def _schreibe_atomar(ziel: Path, inhalt: str | bytes) -> None:
    # Erst in eine Nachbardatei, dann umbenennen: die Seite liest sonst
    # gelegentlich eine halb geschriebene Datei.
    tmp = ziel.with_name(ziel.name + ".tmp")
    if isinstance(inhalt, bytes):
        tmp.write_bytes(inhalt)
    else:
        tmp.write_text(inhalt, encoding="utf-8")
    os.replace(tmp, ziel)


def _schreibe_falls_anders(ziel: Path, inhalt: str | bytes) -> None:
    try:
        alt = ziel.read_bytes()
    except OSError:
        alt = None
    neu = inhalt if isinstance(inhalt, bytes) else inhalt.encode("utf-8")
    if alt != neu:
        _schreibe_atomar(ziel, inhalt)


def _lade_parklogo(ordner: Path, url: str, oeffnen=None) -> bool:
    """Park-Logo einmal laden. Gibt zurueck, ob eines lokal vorliegt.

    Geladen wird nur, wenn sich die Adresse geaendert hat; danach reicht die
    lokale Datei, auch ohne Internet. Ein Fehler laesst ein vorhandenes Logo
    stehen.
    """
    ziel = ordner / "park-logo"
    merker = ordner / "park-logo.url"
    vorhanden = ziel.exists()
    if not url:
        return vorhanden
    try:
        if vorhanden and merker.read_text(encoding="utf-8").strip() == url:
            return True
    except OSError:
        pass
    # Offline nicht bei jedem Herzschlag 15 Sekunden auf einen Download warten.
    jetzt = time.time()
    if jetzt - _letzter_versuch.get(url, 0.0) < LOGO_RETRY_SECONDS:
        return vorhanden
    _letzter_versuch[url] = jetzt
    if not url.startswith("https://"):
        log.warning("station logo ignored, not https: %s", url)
        return vorhanden
    try:
        if oeffnen is None:
            from .tls import open_url as oeffnen
        anfrage = urllib.request.Request(url, headers={"User-Agent": "liftpic-sync-station"})
        with oeffnen(anfrage, timeout=15) as antwort:
            art = (antwort.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            daten = antwort.read(LOGO_MAX_BYTES + 1)
        if art not in LOGO_TYPES or not daten or len(daten) > LOGO_MAX_BYTES:
            log.warning("station logo rejected (%s, %s bytes)", art, len(daten))
            return vorhanden
        _schreibe_atomar(ziel, daten)
        _schreibe_atomar(merker, url)
        return True
    except Exception as exc:  # offline usw. - beim naechsten Herzschlag wieder
        log.info("station logo not loaded yet: %s", exc)
        return vorhanden


PAGE_REV = hashlib.sha256(PAGE.encode("utf-8")).hexdigest()[:12]


def schreibe_station(ordner: Path, stand: dict, logo_url: str = "", oeffnen=None) -> None:
    ordner.mkdir(parents=True, exist_ok=True)
    # Die Seite zuerst, dann status.js: wer eine frische status.js sieht, hat
    # auch die passende Seite.
    _schreibe_falls_anders(ordner / "index.html", PAGE.replace("__PAGE_REV__", PAGE_REV))
    _schreibe_falls_anders(ordner / "liftpic-logo.png", base64.b64decode(LIFTPIC_LOGO_PNG_B64))
    # Fuer die Verknuepfungen (Desktop, Startmenue, Taskleiste).
    _schreibe_falls_anders(ordner / "station.ico", base64.b64decode(STATION_ICON_ICO_B64))

    stand = dict(stand)
    stand["page_rev"] = PAGE_REV
    # Ob ein Park-Logo da ist; ohne blendet die Seite den Platz aus.
    stand["park_logo"] = _lade_parklogo(ordner, logo_url, oeffnen)

    daten = json.dumps(stand, ensure_ascii=True, default=str, separators=(",", ":"))
    # `</` maskieren, falls ein Text je so etwas enthaelt.
    daten = daten.replace("</", "<\\/")
    _schreibe_atomar(ordner / "status.js", f"window.__station&&window.__station({daten});\n")
