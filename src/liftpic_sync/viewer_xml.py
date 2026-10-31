"""QR-Code und Preis im Verkaufsprogramm (Settings.xml) aus der Ferne lesen und setzen.

Bisher ging das nur per AnyDesk: Datei öffnen, Zeile ändern, Programm neu starten.
Jetzt kommt ein Auftrag aus dem CRM (`settings.viewer_auftrag`), der Agent schreibt
die Werte und startet das Verkaufsprogramm auf Wunsch neu.

Geändert wird nur der Text zwischen `<Schlüssel>` und `</Schlüssel>`. Die Datei wird
byteweise gelesen und als Latin-1 behandelt, damit Umlaute, BOM und Zeilenenden genau
so bleiben, wie das Verkaufsprogramm sie geschrieben hat. Erlaubt sind nur die
Schlüssel unten, jeweils mit Prüfung des Werts. Vorher wird eine Sicherung angelegt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .camera_settings import sicherung_anlegen

# Ziel des QR-Codes: nur unsere Claim-Seiten oder das alte jpeg4web.
_QR_ZIEL = re.compile(
    r"^(https://liftpictures-fotos(-tarzans)?\.de/[a-z0-9/_-]*claim\?code=|"
    r"(https?://)?www2\.liftpictures\.de/jpeg4web/frame/preview(_mysql)?\.php\?code=)$",
    re.I,
)
SCHLUESSEL = ("QrCodeBeginningString", "EnableQrCodePrintButtons", "PricePrint")
# Darf nie aus der Ferne geaendert werden: davon haengt ab, in welchem Park ein Foto landet.
GESPERRT = {"CustomerNumber", "CustomerNumberPositions", "CodePositions", "CodePositionsInFilename"}
_LEAF = re.compile(r"<([A-Za-z][A-Za-z0-9_]{0,60})>([^<\r\n]{0,300})</\1>")


@dataclass
class ViewerErgebnis:
    geschrieben: dict[str, str] = field(default_factory=dict)
    abgelehnt: dict[str, str] = field(default_factory=dict)
    sicherung: str | None = None
    fehler: str | None = None


def _tag(name: str) -> re.Pattern[str]:
    return re.compile(rf"<{name}>([^<]*)</{name}>")


def lies_viewer(xml_datei: Path | None) -> dict | None:
    """Die aktuellen Werte für das CRM, oder None wenn es keine Datei gibt."""
    if xml_datei is None or not Path(xml_datei).exists():
        return None
    try:
        text = Path(xml_datei).read_bytes().decode("latin-1")
    except OSError:
        return None
    werte: dict[str, object] = {}
    for name in SCHLUESSEL:
        treffer = _tag(name).search(text)
        if treffer:
            werte[name] = treffer.group(1).strip()
    if "EnableQrCodePrintButtons" in werte:
        werte["EnableQrCodePrintButtons"] = str(werte["EnableQrCodePrintButtons"]).lower() == "true"
    return werte


def lies_alle(xml_datei: Path | None) -> dict[str, str] | None:
    """Alle einfachen Einträge `<Name>Wert</Name>` (jeweils der erste), für das CRM."""
    if xml_datei is None or not Path(xml_datei).exists():
        return None
    try:
        text = Path(xml_datei).read_bytes().decode("latin-1")
    except OSError:
        return None
    werte: dict[str, str] = {}
    for treffer in _LEAF.finditer(text):
        werte.setdefault(treffer.group(1), treffer.group(2).strip())
        if len(werte) >= 400:
            break
    return werte


def _pruefe(name: str, roh: object) -> tuple[str | None, str | None]:
    """(Text für die Datei, Ablehnungsgrund)."""
    if name in GESPERRT:
        return None, "Bildcode-Einstellung – nur am PC änderbar"
    if name == "EnableQrCodePrintButtons":
        if not isinstance(roh, bool):
            return None, "muss an oder aus sein"
        return ("true" if roh else "false"), None
    if name == "PricePrint":
        try:
            zahl = float(roh)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None, "keine Zahl"
        if not (0 < zahl <= 100):
            return None, "ausserhalb von 0 bis 100"
        return (str(int(zahl)) if zahl == int(zahl) else f"{zahl:g}"), None
    if name == "QrCodeBeginningString":
        text = str(roh or "").strip()
        if not _QR_ZIEL.match(text):
            return None, "kein erlaubtes QR-Ziel"
        return text, None
    # Alle anderen vorhandenen Einträge: einfacher Text, Zahl oder an/aus.
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,60}", name):
        return None, "kein gueltiger Name"
    if isinstance(roh, bool):
        return ("true" if roh else "false"), None
    text = str(roh if roh is not None else "").strip()
    if len(text) > 300 or any(z in text for z in "<>&\r\n"):
        return None, "ungueltiger Wert"
    return text, None


def schreibe_viewer(xml_datei: Path | None, werte: dict) -> ViewerErgebnis:
    ergebnis = ViewerErgebnis()
    if xml_datei is None or not Path(xml_datei).exists():
        ergebnis.fehler = "Settings.xml des Verkaufsprogramms nicht gefunden"
        return ergebnis

    pfad = Path(xml_datei)
    text = pfad.read_bytes().decode("latin-1")
    geplant: dict[str, str] = {}
    for name, roh in werte.items():
        neu, grund = _pruefe(str(name), roh)
        if grund:
            ergebnis.abgelehnt[str(name)] = grund
        elif not _tag(str(name)).search(text):
            ergebnis.abgelehnt[str(name)] = "steht nicht in der Datei"
        else:
            geplant[str(name)] = neu  # type: ignore[assignment]

    if not geplant:
        ergebnis.fehler = "nichts zu schreiben" if not ergebnis.abgelehnt else "alle Werte abgelehnt"
        return ergebnis

    ergebnis.sicherung = str(sicherung_anlegen(pfad))
    for name, neu in geplant.items():
        text = _tag(name).sub(lambda _m, n=name, v=neu: f"<{n}>{v}</{n}>", text)
        ergebnis.geschrieben[name] = neu
    pfad.write_bytes(text.encode("latin-1"))
    return ergebnis
