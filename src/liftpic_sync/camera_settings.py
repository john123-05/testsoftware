"""Die Einstellungen der Kamera auslesen.

Die Kamera ist eine GigE-Kamera von The Imaging Source (auf dem Testrechner
eine DFK 33GX545). Ihre Einstellungen stehen nicht in der Kamera, sondern in
einer XML-Datei, die die Kamerasoftware beim Start einliest - bei 3GerTis ist
das `trigger.xml`, der Name steht in `3gertis.ini` unter `xml_file`.

Der Aufbau dieser Datei ist maschinenfreundlich und menschenfeindlich: jede
Eigenschaft ist eine GUID, der Name steht als Attribut daneben.

    <item guid="{284C0E09-...}" name="Saturation">
      <element guid="{B57D3000-...}" name="Value">
        <itf guid="{99B44940-...}" value="120.3125" />
      </element>
    </item>

Gelesen wird alles Interessante, geschrieben nur eine bewusst kleine Auswahl
(siehe SCHREIBBAR). Eine falsch gesetzte Belichtung macht einen ganzen
Betriebstag unbrauchbar und faellt niemandem sofort auf - deshalb gilt hier:
jeder Schreibvorgang legt vorher eine Sicherung an, jeder Wert wird in feste
Grenzen gezwungen, und geschrieben wird immer nur das EINE Attribut, nie die
ganze Datei neu.
"""

from __future__ import annotations

import configparser
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Was wir ans Dashboard melden. Bewusst eine feste Auswahl statt "alles":
# `trigger.xml` enthaelt auch Netzwerk-Feintuning und GPIO-Belegung, das
# gehoert nicht auf eine Bedienseite.
INTERESSANT = (
    "Exposure",
    "Gain",
    "WhiteBalance",
    "Brightness",
    "Contrast",
    "Saturation",
    "Gamma",
    "Sharpness",
    "Hue",
    "Denoise",
    "Tone Mapping",
    "Highlight Reduction",
    "Color Correction Matrix",
)


@dataclass
class Kamera:
    """Was wir ueber die Kamera und ihre Einstellungen wissen."""

    modell: str | None = None
    seriennummer: str | None = None
    videoformat: str | None = None
    bilder_pro_sekunde: float | None = None
    quelle: str | None = None          # Pfad der gelesenen XML-Datei
    programm: str | None = None        # welche Software sie steuert
    werte: dict[str, dict[str, float | int | str | bool]] = field(default_factory=dict)
    fehler: str | None = None

    def as_dict(self) -> dict:
        return {
            "modell": self.modell,
            "seriennummer": self.seriennummer,
            "videoformat": self.videoformat,
            "fps": self.bilder_pro_sekunde,
            "quelle": self.quelle,
            "programm": self.programm,
            "werte": self.werte,
            "fehler": self.fehler,
        }


def _zahl(text: str) -> float | int | str | bool:
    """XML kennt nur Text. Wir wollen Zahlen, wo es welche sind."""
    roh = text.strip()
    if roh in ("0", "1"):
        # Kann beides sein. Als Zahl zurueckgeben, die Anzeige entscheidet
        # anhand des Namens, ob sie daraus einen Schalter macht.
        return int(roh)
    try:
        wert = float(roh)
    except ValueError:
        return roh
    return int(wert) if wert.is_integer() and abs(wert) < 1e9 else wert


def _xml_pfad(ini: Path) -> Path | None:
    """Welche XML-Datei liest die Kamerasoftware? Steht in ihrer INI."""
    try:
        parser = configparser.ConfigParser(strict=False, interpolation=None)
        parser.read(ini, encoding="utf-8-sig")
        name = parser.get("device", "xml_file", fallback=None)
    except Exception as exc:
        log.debug("could not read %s: %s", ini, exc)
        return None
    if not name:
        return None
    kandidat = Path(name)
    return kandidat if kandidat.is_absolute() else ini.parent / kandidat


def lies_kamera(xml_datei: Path, programm: str | None = None) -> Kamera:
    """Modell, Format und die interessanten Eigenschaften aus der XML holen."""
    kamera = Kamera(quelle=str(xml_datei), programm=programm)

    if not xml_datei.exists():
        kamera.fehler = f"{xml_datei} gibt es nicht"
        return kamera

    try:
        wurzel = ET.parse(xml_datei).getroot()
    except Exception as exc:
        # Eine unlesbare Datei ist ein Befund, kein Grund zum Abstuerzen -
        # der Herzschlag darf daran nie scheitern.
        kamera.fehler = f"nicht lesbar: {exc}"
        log.warning("camera settings: %s could not be parsed: %s", xml_datei, exc)
        return kamera

    geraet = wurzel.find("device")
    if geraet is not None:
        name = geraet.get("name") or geraet.get("base_name") or ""
        # "DFK 33GX545 [Imst] 42320366" -> Modell und Seriennummer trennen
        eindeutig = geraet.get("unique_name") or name
        treffer = re.search(r"(\d{6,})\s*$", eindeutig.strip())
        if treffer:
            kamera.seriennummer = treffer.group(1)
        kamera.modell = re.sub(r"\s*\[.*?\]\s*", " ", name).strip() or None

        formatknoten = geraet.find("videoformat")
        if formatknoten is not None and formatknoten.text:
            kamera.videoformat = formatknoten.text.strip()
        fps = geraet.find("fps")
        if fps is not None and fps.text:
            try:
                kamera.bilder_pro_sekunde = round(float(fps.text), 2)
            except ValueError:
                pass

    for item in wurzel.iter("item"):
        name = (item.get("name") or "").strip()
        if name not in INTERESSANT:
            continue
        eintrag: dict[str, float | int | str | bool] = {}
        for element in item.findall("element"):
            schluessel = (element.get("name") or "").strip()
            itf = element.find("itf")
            if not schluessel or itf is None:
                continue
            wert = itf.get("value")
            if wert is None:
                continue
            eintrag[schluessel] = _zahl(wert)
        if eintrag:
            # Mehrfach vorkommende Namen (Exposure taucht mit Auto und Value
            # in getrennten Bloecken auf) zusammenfuehren statt ueberschreiben.
            kamera.werte.setdefault(name, {}).update(eintrag)

    if not kamera.werte:
        kamera.fehler = "keine bekannten Eigenschaften gefunden"
    return kamera


# Der Herzschlag geht alle paar Sekunden raus. Eine 49-KB-XML jedes Mal neu zu
# lesen waere Verschwendung, also merken wir uns das Ergebnis und lesen nur neu,
# wenn sich die Datei wirklich geaendert hat.
_zwischenspeicher: dict[str, tuple[float, dict]] = {}


def xml_pfad_fuer(settings) -> Path | None:
    """Welche Datei liest die Kamerasoftware dieses Automaten?"""
    exe = getattr(settings, "camera_exe", None)
    if exe is None:
        return None
    ordner = Path(exe).parent
    xml_datei = _xml_pfad(ordner / "3gertis.ini")
    if xml_datei is None or not xml_datei.exists():
        xml_datei = ordner / "trigger.xml"
    return xml_datei


def kamera_status(settings) -> dict | None:
    """Fuer den Herzschlag: was steuert die Kamera, und wie ist sie eingestellt?

    Gibt `None` zurueck, wenn auf diesem Automaten keine Kamerasoftware
    eingerichtet ist - dann erscheint im Dashboard auch keine Kameraseite.
    """
    exe = getattr(settings, "camera_exe", None)
    if exe is None:
        return None

    exe = Path(exe)
    ordner = exe.parent
    programm = exe.name

    # Erst den in der INI genannten Namen versuchen, dann den ueblichen.
    xml_datei = _xml_pfad(ordner / "3gertis.ini")
    if xml_datei is None or not xml_datei.exists():
        xml_datei = ordner / "trigger.xml"

    try:
        schluessel = str(xml_datei)
        try:
            stand = xml_datei.stat().st_mtime
        except OSError:
            stand = 0.0
        gemerkt = _zwischenspeicher.get(schluessel)
        if gemerkt is not None and gemerkt[0] == stand:
            return gemerkt[1]

        ergebnis = lies_kamera(xml_datei, programm=programm).as_dict()
        _zwischenspeicher[schluessel] = (stand, ergebnis)
        return ergebnis
    except Exception as exc:  # darf den Herzschlag nie kosten
        log.warning("camera settings failed: %s", exc)
        return {"programm": programm, "fehler": str(exc), "werte": {}}


# ---------------------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------------------

# Was aus der Ferne veraendert werden darf, und in welchen Grenzen.
#
# Die Grenzen sind bewusst enger gefasst als das, was die Kamera technisch
# zulaesst. Wir kennen ihre echten Bereiche nicht - `trigger.xml` speichert nur
# Werte, keine Bereiche - und ein Wert, den die Kamera nicht annimmt, faellt
# erst beim naechsten Gast auf. Lieber ein Regler, der zu frueh anschlaegt, als
# ein Betriebstag mit unbrauchbaren Bildern.
#
# (Eigenschaft, Element) -> (kleinster, groesster Wert)
SCHREIBBAR: dict[tuple[str, str], tuple[float, float]] = {
    ("Brightness", "Value"): (-64.0, 64.0),
    ("Contrast", "Value"): (-64.0, 64.0),
    ("Saturation", "Value"): (0.0, 200.0),
    ("Hue", "Value"): (-180.0, 180.0),
    ("Gamma", "Value"): (0.1, 3.0),
    ("Sharpness", "Value"): (0.0, 100.0),
    ("Denoise", "Value"): (0.0, 100.0),
    ("Exposure", "Value"): (0.00002, 2.0),          # Sekunden
    ("Exposure", "Auto"): (0.0, 1.0),
    ("Exposure", "Auto Reference"): (0.0, 255.0),
    ("Gain", "Auto"): (0.0, 1.0),
    ("Gain", "Auto Max Value"): (0.0, 96.0),
    ("WhiteBalance", "Auto"): (0.0, 1.0),
    ("Tone Mapping", "Enable"): (0.0, 1.0),
    ("Highlight Reduction", "Enable"): (0.0, 1.0),
}


@dataclass
class Schreibergebnis:
    """Was beim Schreiben wirklich passiert ist."""

    geschrieben: dict[str, float] = field(default_factory=dict)
    abgelehnt: dict[str, str] = field(default_factory=dict)
    sicherung: str | None = None
    fehler: str | None = None

    @property
    def erfolgreich(self) -> bool:
        return self.fehler is None and bool(self.geschrieben)

    def as_dict(self) -> dict:
        return {
            "geschrieben": self.geschrieben,
            "abgelehnt": self.abgelehnt,
            "sicherung": self.sicherung,
            "fehler": self.fehler,
        }


def _als_text(wert: float) -> str:
    """Wie die Kamera Zahlen schreibt: ganze Zahlen ohne Komma."""
    if float(wert).is_integer():
        return str(int(wert))
    return repr(round(float(wert), 9))


def sicherung_anlegen(xml_datei: Path) -> Path:
    """Vor jeder Aenderung. Der Rueckweg muss existieren, bevor er gebraucht wird."""
    from datetime import datetime

    stempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    ziel = xml_datei.with_name(f"{xml_datei.name}.sicherung-{stempel}")
    ziel.write_bytes(xml_datei.read_bytes())
    return ziel


def schreibe_werte(xml_datei: Path, werte: dict[str, float]) -> Schreibergebnis:
    """Einzelne Kamerawerte in die XML schreiben.

    `werte` kommt als flache Zuordnung `"Eigenschaft.Element" -> Zahl`, also
    zum Beispiel `{"Saturation.Value": 130, "Gamma.Value": 0.9}`.

    Geaendert wird ausschliesslich das `value`-Attribut der betroffenen Zeile.
    Die Datei wird nicht neu erzeugt: sie enthaelt GUIDs, Reihenfolgen und
    Nachkommastellen, auf die sich die Kamerasoftware verlaesst. Ein
    "schoener" neu geschriebenes XML waere das erste, was kaputt geht.
    """
    ergebnis = Schreibergebnis()

    if not xml_datei.exists():
        ergebnis.fehler = f"{xml_datei} gibt es nicht"
        return ergebnis

    # Erst pruefen, dann anfassen. Eine Sicherung fuer einen Auftrag anzulegen,
    # der ohnehin komplett abgelehnt wird, waere nur Muell im Ordner.
    geplant: dict[tuple[str, str], float] = {}
    for schluessel, roh in werte.items():
        if "." not in schluessel:
            ergebnis.abgelehnt[schluessel] = "kein gueltiger Name"
            continue
        eigenschaft, _, element = schluessel.partition(".")
        grenzen = SCHREIBBAR.get((eigenschaft, element))
        if grenzen is None:
            ergebnis.abgelehnt[schluessel] = "darf aus der Ferne nicht geaendert werden"
            continue
        try:
            zahl = float(roh)
        except (TypeError, ValueError):
            ergebnis.abgelehnt[schluessel] = "keine Zahl"
            continue
        klein, gross = grenzen
        if not (klein <= zahl <= gross):
            ergebnis.abgelehnt[schluessel] = f"ausserhalb von {klein} bis {gross}"
            continue
        geplant[(eigenschaft, element)] = zahl

    if not geplant:
        if not ergebnis.abgelehnt:
            ergebnis.fehler = "nichts zu schreiben"
        return ergebnis

    try:
        baum = ET.parse(xml_datei)
    except Exception as exc:
        ergebnis.fehler = f"nicht lesbar: {exc}"
        return ergebnis

    wurzel = baum.getroot()
    gefunden: dict[tuple[str, str], object] = {}
    for item in wurzel.iter("item"):
        eigenschaft = (item.get("name") or "").strip()
        for element in item.findall("element"):
            name = (element.get("name") or "").strip()
            itf = element.find("itf")
            if itf is None:
                continue
            if (eigenschaft, name) in geplant:
                gefunden[(eigenschaft, name)] = itf

    for schluessel in geplant:
        if schluessel not in gefunden:
            ergebnis.abgelehnt[f"{schluessel[0]}.{schluessel[1]}"] = "in dieser Kamera nicht vorhanden"

    zu_schreiben = {k: v for k, v in geplant.items() if k in gefunden}
    if not zu_schreiben:
        ergebnis.fehler = "keiner der Werte kommt in dieser Kamera vor"
        return ergebnis

    try:
        ergebnis.sicherung = str(sicherung_anlegen(xml_datei))
    except Exception as exc:
        # Ohne Sicherung wird nicht geschrieben. Das ist keine Vorsicht,
        # das ist die Bedingung.
        ergebnis.fehler = f"Sicherung nicht moeglich, es wurde nichts geaendert: {exc}"
        return ergebnis

    for schluessel, zahl in zu_schreiben.items():
        gefunden[schluessel].set("value", _als_text(zahl))
        ergebnis.geschrieben[f"{schluessel[0]}.{schluessel[1]}"] = zahl

    try:
        # Erst daneben schreiben, dann ersetzen. Ein Stromausfall mitten im
        # Schreiben hinterlaesst sonst eine halbe Datei, und die Kamera
        # startet beim naechsten Mal gar nicht mehr.
        vorlaeufig = xml_datei.with_suffix(xml_datei.suffix + ".neu")
        baum.write(vorlaeufig, encoding="utf-8", xml_declaration=False)
        vorlaeufig.replace(xml_datei)
        _zwischenspeicher.clear()
    except Exception as exc:
        ergebnis.fehler = f"Schreiben fehlgeschlagen: {exc}"
        ergebnis.geschrieben.clear()
    return ergebnis
