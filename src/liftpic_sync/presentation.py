"""Liftpictures Presentation: Nachbau der Praesentation des Verkaufsprogramms.

Das Verkaufsprogramm (PhotoViewerFacebook, `SlideshowWindow`) zeigt auf dem
zweiten Bildschirm die neuesten Fotos als Raster. Seine QR-Codes enthalten
aber nur den Dateinamen ("i00057") - gedacht fuer den Suchscanner am Automaten,
mit dem Handy laesst sich damit nichts kaufen. Das ist fest programmiert
(`SlideshowThumbnailControl.Load`), keine Einstellung aendert es.

Dieser Nachbau sieht genauso aus - er liest dieselben Split-Werte aus der
`Settings.xml` - und setzt auf jedes Foto einen QR-Code mit dem echten
Kauf-Link. Der Code entsteht nach derselben Formel wie beim Hochladen
(scanner.py, Modus "online"), stimmt also auch fuer Fotos vom Vortag.

Der Agent schreibt nach `presentation_dir` (Vorgabe C:\\liftpic\\presentation):
`index.html`, `photos.js` (Stand) und das Wasserzeichen. Edge zeigt die Seite
im Vollbild auf dem zweiten Monitor (scripts/presentation_einrichten.ps1).
Laeuft ohne Internet; die Fotos kommen direkt aus dem Fotoordner.

Lizenz: Fotos zeigt die Seite nur, wenn der PC mit dem Dashboard gekoppelt ist
und die Praesentation dort fuer ihn freigeschaltet ist (`presentation_enabled`).
Sonst zeigt sie einen Hinweis statt Fotos.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from .filename_codec import build_legacy_filename, viewer_file_code
from .presentation_design import fotos_benoetigt, gestaltung, lies_design
from .presentation_page import PAGE
from .qr import qr_svg
from .viewer_xml import lies_alle

log = logging.getLogger(__name__)

PAGE_REV = hashlib.sha256(PAGE.encode("utf-8")).hexdigest()[:12]
BILDTYPEN = {".jpg", ".jpeg"}
# Eine Datei, die gerade noch geschrieben wird, nicht anzeigen.
STABIL_SEKUNDEN = 1.5


# ------------------------------------------------------------------ Aussehen

def _farbe(wert: str | None, standard: str) -> str:
    wert = (wert or "").strip()
    return wert if re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", wert) else standard


def _zahl(wert: str | None, standard: int, kleinst: int, groesst: int) -> int:
    try:
        return max(kleinst, min(groesst, int(float((wert or "").strip()))))
    except ValueError:
        return standard


def _ja(wert: str | None, standard: bool) -> bool:
    wert = (wert or "").strip().lower()
    if wert in ("true", "1", "yes", "ja"):
        return True
    if wert in ("false", "0", "no", "nein"):
        return False
    return standard


def stil(viewer: dict | None) -> dict:
    """Die Split-Werte des Verkaufsprogramms, mit dessen Vorgaben."""
    v = viewer or {}
    return {
        "background": _farbe(v.get("SplitBackgroundColor"), "#3977BD"),
        "columns": _zahl(v.get("SplitNumberColumns"), 3, 1, 6),
        "rows": _zahl(v.get("SplitNumberRows"), 2, 1, 6),
        "border": _zahl(v.get("SplitBorder"), 20, 0, 200),
        "show_label": _ja(v.get("SplitShowLabel"), True),
        "label_size": _zahl(v.get("SplitLabelSize"), 30, 8, 200),
        "label_color": _farbe(v.get("SplitLabelColor"), "#FFFFFF"),
        "ticker": _ja(v.get("EnableSplitTicker"), True),
        "ticker_text": (v.get("SplitTickerText") or "Scan your photo..!")[:300],
        "ticker_color": _farbe(v.get("SplitTickerTextColor"), "#000000"),
        "ticker_background": _farbe(v.get("SplitTickerBackgroundColor"), "#FFFFFF"),
        "ticker_size": _zahl(v.get("SplitTickerTextSize"), 40, 8, 300),
        "ticker_speed": _zahl(v.get("SplitTickerSpeed"), 50, 1, 2000),
        "ticker_height": _zahl(v.get("SplitTickerHeight"), 40, 8, 400),
        # Utils.CropImage: so viele Pixel links/rechts bzw. oben/unten weg.
        "crop_x": _zahl(v.get("PreviewCropX"), 0, 0, 5000),
        "crop_y": _zahl(v.get("PreviewCropY"), 0, 0, 5000),
    }


def gueltige_qr_basis(text: str) -> bool:
    """Nur Liftpictures-Claim-Seiten - wie im CRM geprueft."""
    return bool(re.fullmatch(r"https://liftpictures-fotos(-tarzans)?\.de/[a-z0-9/_-]*claim\?code=", text or "", re.I))


def claim_basis(viewer: dict | None, park_slug: str, override: str = "") -> tuple[str, str]:
    """Link-Anfang und -Ende. Wie in der Einzelansicht des Verkaufsprogramms
    aus QrCodeBeginningString/QrCodeEndingString - aber nur, wenn das ein
    echter Link ist. Die alte jpeg4web-Adresse ohne https fuehrte ins Leere."""
    if override and gueltige_qr_basis(override.strip()):
        return override.strip(), ""
    v = viewer or {}
    anfang = (v.get("QrCodeBeginningString") or "").strip()
    ende = (v.get("QrCodeEndingString") or "").strip()
    if not anfang.lower().startswith("https://") or "jpeg4web" in anfang.lower():
        return f"https://liftpictures-fotos.de/{park_slug}/claim?code=", ""
    return anfang, ende


# ----------------------------------------------------------------- Fotos

def abholcode(customer_code: str, bild: Path, positionen: str, mtime: float) -> str:
    """Der 16-stellige Code, genau wie beim Hochladen im Modus "online"."""
    nummer = viewer_file_code(bild.name, positionen)
    aufgenommen = datetime.fromtimestamp(mtime).astimezone()
    name = build_legacy_filename(
        customer_code=customer_code,
        capture_id=nummer,
        captured_at=aufgenommen,
        file_code_positions="1,2,3,4",
    )
    return Path(name.filename).stem


def neueste_fotos(ordner: Path, anzahl: int, jetzt: float) -> list[tuple[Path, float]]:
    try:
        eintraege = [
            (Path(e.path), e.stat().st_mtime)
            for e in os.scandir(ordner)
            if e.is_file() and Path(e.name).suffix.lower() in BILDTYPEN
        ]
    except OSError:
        return []
    eintraege = [(p, m) for p, m in eintraege if jetzt - m >= STABIL_SEKUNDEN]
    eintraege.sort(key=lambda t: (t[1], t[0].name), reverse=True)
    return eintraege[:anzahl]


# -------------------------------------------------------------- Schreiben

def _atomar(ziel: Path, inhalt: str | bytes) -> None:
    tmp = ziel.with_name(ziel.name + ".tmp")
    if isinstance(inhalt, bytes):
        tmp.write_bytes(inhalt)
    else:
        tmp.write_text(inhalt, encoding="utf-8")
    os.replace(tmp, ziel)


class Praesentation:
    """Haelt den Ordner aktuell. Einmal anlegen, dann `schreibe()` im Takt."""

    def __init__(self, ordner: Path):
        self.ordner = ordner
        self._fotos: dict[tuple[str, float], dict] = {}
        self._signatur: str | None = None
        self._logo: tuple[str, float, int] | None = None
        self.anzahl = 0
        self.link_anfang = ""

    def _logo_datei(self, url: str, oeffnen=None) -> str | None:
        """Logo (z. B. Kalahari) einmal laden und lokal ablegen - wie bei der Station."""
        from .station import _lade_parklogo
        if not _lade_parklogo(self.ordner, url or "", oeffnen):
            return None
        try:
            stand = int((self.ordner / "park-logo").stat().st_mtime)
        except OSError:
            return None
        return f"park-logo?v={stand}"

    def _wasserzeichen(self, quelle: str | None) -> str | None:
        if not quelle:
            return None
        pfad = Path(quelle)
        try:
            info = pfad.stat()
        except OSError:
            return None
        name = "preview-logo" + (pfad.suffix.lower() or ".png")
        kennung = (str(pfad), info.st_mtime, info.st_size)
        if kennung != self._logo or not (self.ordner / name).exists():
            shutil.copyfile(pfad, self.ordner / (name + ".tmp"))
            os.replace(self.ordner / (name + ".tmp"), self.ordner / name)
            self._logo = kennung
        return f"{name}?v={int(info.st_mtime)}"

    def schreibe(self, *, raw_dir: Path, viewer_xml: Path | None, customer_code: str,
                 positionen: str, park_slug: str, lizenziert: bool,
                 grund: str = "", qr_basis: str = "", gueltig_bis: str = "",
                 design: str | dict | None = None, logo_url: str = "", oeffnen=None,
                 jetzt: float | None = None) -> bool:
        """Gibt zurueck, ob sich etwas geaendert hat."""
        jetzt = time.time() if jetzt is None else jetzt
        self.ordner.mkdir(parents=True, exist_ok=True)
        seite = PAGE.replace("__PAGE_REV__", PAGE_REV)
        ziel = self.ordner / "index.html"
        try:
            alt = ziel.read_text(encoding="utf-8")
        except OSError:
            alt = None
        if alt != seite:
            _atomar(ziel, seite)

        viewer = lies_alle(viewer_xml)
        s = gestaltung(stil(viewer), lies_design(design))
        s["viewer_logo"] = self._wasserzeichen((viewer or {}).get("SplitPreviewLogo"))
        s["logo"] = self._logo_datei(s.get("logo_url") or logo_url, oeffnen)
        s.pop("logo_url", None)
        anfang, ende = claim_basis(viewer, park_slug, qr_basis)

        fotos: list[dict] = []
        if lizenziert:
            for bild, mtime in neueste_fotos(raw_dir, fotos_benoetigt(s), jetzt):
                schluessel = (str(bild), mtime)
                eintrag = self._fotos.get(schluessel)
                if eintrag is None:
                    try:
                        nummer = viewer_file_code(bild.name, positionen)
                        code = abholcode(customer_code, bild, positionen, mtime)
                    except ValueError:
                        continue  # Datei passt nicht zum Namensschema der Kamera
                    url = f"{anfang}{code}{ende}"
                    eintrag = {
                        "key": f"{bild.name}:{int(mtime)}",
                        "src": bild.as_uri(),
                        "number": nummer,
                        "time": datetime.fromtimestamp(mtime).strftime("%H:%M"),
                        "ts": int(mtime),
                        "code": code,
                        "url": url,
                        "qr": qr_svg(url, border=2),
                    }
                    self._fotos[schluessel] = eintrag
                fotos.append(eintrag)
            if len(self._fotos) > 300:
                aktuell = {f["key"] for f in fotos}
                self._fotos = {k: v for k, v in self._fotos.items() if v["key"] in aktuell}

        self.anzahl = len(fotos)
        self.link_anfang = anfang
        stand = {"page_rev": PAGE_REV, "licensed": lizenziert, "reason": grund,
                 "valid_until": gueltig_bis or None, "style": s, "photos": fotos}
        signatur = json.dumps(stand, sort_keys=True)
        if signatur == self._signatur and (self.ordner / "photos.js").exists():
            return False
        daten = json.dumps(stand, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")
        _atomar(self.ordner / "photos.js", f"window.__presentation&&window.__presentation({daten});\n")
        self._signatur = signatur
        return True
