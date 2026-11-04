"""Liftpictures Station: lokale Statusseite auf dem Automaten-Bildschirm.

Der Agent schreibt bei jedem Herzschlag zwei Dateien in `station_dir`
(Vorgabe `C:\\liftpic\\station`):

- `index.html`: die Seite selbst (aus `station_page.PAGE`), nur wenn sie sich
  geaendert hat.
- `status.js`: der aktuelle Stand als `window.__station({...})`.

Die Seite laedt `status.js` alle paar Sekunden neu. Weil beides lokale Dateien
sind (file://), funktioniert sie ohne Internet - genau dann, wenn man sie am
dringendsten braucht. Bleibt `status.js` stehen, erkennt die Seite das selbst
("Monitoring stopped") und sagt, dass der PC neu gestartet werden soll.

Geoeffnet wird sie per Autostart-Verknuepfung, z. B.:
  msedge --app=file:///C:/liftpic/station/index.html --start-fullscreen
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .station_page import PAGE


def _schreibe_atomar(ziel: Path, text: str) -> None:
    # Erst in eine Nachbardatei, dann umbenennen: die Seite liest sonst
    # gelegentlich eine halb geschriebene Datei und zeigt einen Fehler.
    tmp = ziel.with_name(ziel.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, ziel)


def schreibe_station(ordner: Path, stand: dict) -> None:
    ordner.mkdir(parents=True, exist_ok=True)
    seite = ordner / "index.html"
    try:
        alt = seite.read_text(encoding="utf-8")
    except OSError:
        alt = None
    if alt != PAGE:
        _schreibe_atomar(seite, PAGE)

    daten = json.dumps(stand, ensure_ascii=True, default=str, separators=(",", ":"))
    # `</` maskieren, falls ein Text je so etwas enthaelt.
    daten = daten.replace("</", "<\\/")
    _schreibe_atomar(ordner / "status.js", f"window.__station&&window.__station({daten});\n")
