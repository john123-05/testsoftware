"""Liftpictures Kiosk: das neue Verkaufsprogramm am Automaten.

Nachfolger von PhotoViewerFacebook. Die Oberflaeche (kiosk_app/, React) laeuft
in Liftpictures Display (`--kiosk`, WebView2). Der Agent liefert ihr alles als
Dateien im Kiosk-Ordner (Vorgabe C:\\liftpic\\kiosk-data):

- data.js    `window.__kiosk({...})`: Lizenz, Einstellungen aus dem CRM und die
             Fotos des Betriebstags mit Bildnummer, Abholcode und Kauf-Link.
- host.json  Was Liftpictures Display fuer die Geraete braucht: Fotoordner,
             Statistic.txt, PrintCount.txt, Verkauft-Ordner, Kartenterminal
             (easyzvt.exe ueber die Registry), Muenzgeraet (NRI), Drucker und
             Gesichtserkennung (FaceAiSharp). Die Werte stammen aus der
             Settings.xml des alten Programms - ein Automat steigt ohne Umbau um.
- park-logo  Das Logo des Parks, einmal geladen, offline verfuegbar.

Zurueck schreibt Liftpictures Display `sales/JJJJ-MM-TT.jsonl` (eine Zeile je
Verkauf) und - wie das alte Programm - Statistic.txt, PrintCount.txt und die
verkauften Fotos in den Verkauft-Ordner. Der Agent meldet die Tageszahlen im
Herzschlag; die bestehende Kette (Hochladen, Zahlungen, Dashboard) bleibt.

Lizenz wie bei der Presentation: nur gekoppelt, im CRM freigeschaltet
(`kiosk_enabled`), nicht abgelaufen (`kiosk_valid_until`) und mit Serverkontakt
in den letzten Tagen. Sonst zeigt die App einen Hinweis statt Fotos.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path

from .filename_codec import viewer_file_code
from .presentation import BILDTYPEN, STABIL_SEKUNDEN, _atomar, abholcode, claim_basis
from .viewer_xml import lies_alle

log = logging.getLogger(__name__)

# Ein Betriebstag: die letzten 20 Stunden (Parks ueber Mitternacht).
TAG_SEKUNDEN = 20 * 3600
# Mehr Fotos zeigt kein Gast-Raster sinnvoll an; schuetzt data.js vor Riesenordnern.
MAX_FOTOS = 2500
# Einstellungen aus dem CRM: nur ein Objekt, nicht beliebig gross.
MAX_KONFIG_BYTES = 64_000
# Aus dem CRM duerfen nur diese Bereiche kommen (Rest bestimmt die App selbst).
KONFIG_BEREICHE = {
    "park_name", "currency", "language", "languages", "time_format", "rotation",
    "performance", "express", "theme", "attract", "find", "products", "packages",
    "payments", "cash", "devices", "links", "idle_seconds", "help_seconds",
    "admin_pin", "edition", "print", "vouchers",
}


def fotos_des_tages(ordner: Path, jetzt: float, anzahl: int = MAX_FOTOS) -> list[tuple[Path, float]]:
    """Fotos der letzten TAG_SEKUNDEN, neueste zuerst. Halb geschriebene nicht."""
    try:
        eintraege = []
        with os.scandir(ordner) as it:
            for e in it:
                if not e.is_file() or Path(e.name).suffix.lower() not in BILDTYPEN:
                    continue
                m = e.stat().st_mtime
                if jetzt - TAG_SEKUNDEN <= m <= jetzt - STABIL_SEKUNDEN:
                    eintraege.append((Path(e.path), m))
    except OSError:
        return []
    eintraege.sort(key=lambda t: (t[1], t[0].name), reverse=True)
    return eintraege[:anzahl]


def lies_konfig(roh: str | dict | None) -> dict:
    """Einstellungen aus dem CRM (JSON). Unbrauchbares wird zu {}."""
    if isinstance(roh, dict):
        wert = roh
    else:
        text = (roh or "").strip()
        if not text or len(text) > MAX_KONFIG_BYTES:
            return {}
        try:
            wert = json.loads(text)
        except ValueError:
            log.warning("kiosk config ignored: not JSON")
            return {}
    if not isinstance(wert, dict):
        return {}
    return {k: v for k, v in wert.items() if k in KONFIG_BEREICHE}


def _zahl(wert: str | None, standard: float) -> float:
    try:
        return float(str(wert).replace(",", "."))
    except (TypeError, ValueError):
        return standard


def _ja(wert: str | None, standard: bool = False) -> bool:
    if wert is None or wert == "":
        return standard
    return str(wert).strip().lower() in ("true", "1", "ja", "yes")


def host_einstellungen(*, raw_dir: Path, viewer_xml: Path | None, viewer: dict | None,
                       statistic_file: Path | None, print_count_file: Path | None,
                       sold_dir: Path | None, coin_stats_file: Path | None) -> dict:
    """host.json: Geraete und Pfade fuer Liftpictures Display.

    Alles aus der Settings.xml des alten Programms, mit dessen Vorgaben, wenn
    ein Eintrag fehlt. Das Programm-Verzeichnis (samuel_neu) enthaelt auch die
    Treiber fuer das Muenzgeraet und die Gesichtserkennung.
    """
    v = viewer or {}
    programm = str(Path(viewer_xml).parent) if viewer_xml else r"C:\liftpic\samuel_neu"
    sep = "\\" if "\\" in programm or ":" in programm else "/"
    return {
        "version": 1,
        "photo_dir": str(raw_dir),
        "statistic_file": str(statistic_file) if statistic_file else None,
        "print_count_file": str(print_count_file) if print_count_file else None,
        "sold_dir": str(sold_dir) if sold_dir else None,
        "coin_stats_file": str(coin_stats_file) if coin_stats_file else None,
        "card": {
            "exe": v.get("CreditCardExecutablePath") or r"c:\liftpic\terminal\easyzvt.exe",
            "amount_key": v.get("CreditCardRegistryAmountParameter") or r"Software\GUB\ZVT\Betrag",
            "result_key": v.get("CreditCardRegistryResultParameter") or r"Software\GUB\ZVT\Ergebnis",
            "timeout_seconds": int(_zahl(v.get("CreditCardTimeout"), 120)) or 120,
        },
        "cash": {"lib_dir": programm},
        "printer": {
            "name": v.get("PrinterName") or "",
            "photo_w_mm": _zahl(v.get("PhotoWidth"), 152),
            "photo_h_mm": _zahl(v.get("PhotoHeight"), 102),
            "left_mm": _zahl(v.get("LeftMarginPhoto"), 0),
            "top_mm": _zahl(v.get("TopMarginPhoto"), 0),
            "date": _ja(v.get("EnablePrintDate"), True),
            "time": _ja(v.get("EnablePrintTime"), False),
            "qr": _ja(v.get("EnableQrCode"), True),
            "qr_mm": _zahl(v.get("QrCodeSize"), 16),
            "qr_x_mm": _zahl(v.get("QrCodePositionX"), 125),
            "qr_y_mm": _zahl(v.get("QrCodePositionY"), 80),
            "logo": v.get("SinglePhotoLogoFilename") or "",
            "logo_x_mm": _zahl(v.get("SinglePhotoLogoX"), 3),
            "logo_y_mm": _zahl(v.get("SinglePhotoLogoY"), 5),
            "logo_w_mm": _zahl(v.get("SinglePhotoLogoWidth"), 35),
        },
        "face": {
            "client": f"{programm}{sep}FaceAiSharp{sep}FaceAiSharpClient.exe",
            "photo_dir": v.get("PhotoFolder") or str(raw_dir),
            "threshold": 0.3,
        },
    }


class Kiosk:
    """Haelt den Kiosk-Ordner aktuell. Einmal anlegen, dann `schreibe()` im Takt."""

    def __init__(self, ordner: Path):
        self.ordner = ordner
        self._fotos: dict[tuple[str, float], dict] = {}
        self._signatur: str | None = None
        self._host: str | None = None
        self.anzahl = 0
        self.link_anfang = ""

    def _logo(self, url: str, oeffnen=None) -> str | None:
        from .station import _lade_parklogo
        if not _lade_parklogo(self.ordner, url or "", oeffnen):
            return None
        try:
            stand = int((self.ordner / "park-logo").stat().st_mtime)
        except OSError:
            return None
        return f"park-logo?v={stand}"

    def schreibe(self, *, raw_dir: Path, viewer_xml: Path | None, customer_code: str,
                 positionen: str, park_slug: str, lizenziert: bool, grund: str = "",
                 gueltig_bis: str = "", konfig: str | dict | None = None, qr_basis: str = "",
                 logo_url: str = "", statistic_file: Path | None = None,
                 print_count_file: Path | None = None, sold_dir: Path | None = None,
                 coin_stats_file: Path | None = None, machine_id: str = "",
                 oeffnen=None, jetzt: float | None = None) -> bool:
        """Gibt zurueck, ob sich data.js geaendert hat."""
        jetzt = time.time() if jetzt is None else jetzt
        self.ordner.mkdir(parents=True, exist_ok=True)
        (self.ordner / "sales").mkdir(exist_ok=True)

        viewer = lies_alle(viewer_xml)
        host = json.dumps(host_einstellungen(
            raw_dir=raw_dir, viewer_xml=viewer_xml, viewer=viewer,
            statistic_file=statistic_file, print_count_file=print_count_file,
            sold_dir=sold_dir, coin_stats_file=coin_stats_file,
        ), ensure_ascii=False, indent=2)
        if host != self._host or not (self.ordner / "host.json").exists():
            _atomar(self.ordner / "host.json", host)
            self._host = host

        anfang, ende = claim_basis(viewer, park_slug, qr_basis)
        fotos: list[dict] = []
        if lizenziert:
            for bild, mtime in fotos_des_tages(raw_dir, jetzt):
                schluessel = (str(bild), mtime)
                eintrag = self._fotos.get(schluessel)
                if eintrag is None:
                    try:
                        nummer = viewer_file_code(bild.name, positionen)
                        code = abholcode(customer_code, bild, positionen, mtime)
                    except ValueError:
                        continue  # passt nicht zum Namensschema der Kamera
                    eintrag = {
                        "key": f"{bild.name}:{int(mtime)}",
                        "file": bild.name,
                        "number": nummer,
                        "ts": int(mtime),
                        "code": code,
                        "url": f"{anfang}{code}{ende}",
                    }
                    self._fotos[schluessel] = eintrag
                fotos.append(eintrag)
            if len(self._fotos) > MAX_FOTOS + 500:
                aktuell = {f["key"] for f in fotos}
                self._fotos = {k: v for k, v in self._fotos.items() if v["key"] in aktuell}

        # Was der Agent weiss, ergaenzt die Einstellungen aus dem CRM: Links zur
        # Kaufseite des Parks und das Logo. Das CRM gewinnt, wenn es etwas setzt.
        basis = {
            "links": {
                "download": f"{anfang}{{code}}{ende}",
                "phone_pay": f"{anfang}{{code}}{ende}",
                "phone_search": f"https://liftpictures-fotos.de/{park_slug}/",
            },
        }
        logo = self._logo(logo_url, oeffnen)
        if logo:
            basis["theme"] = {"logo": logo}

        self.anzahl = len(fotos)
        self.link_anfang = anfang
        stand = {
            "licensed": lizenziert, "reason": grund or None,
            "valid_until": gueltig_bis or None, "machine_id": machine_id,
            "base": basis, "config": lies_konfig(konfig), "photos": fotos,
        }
        signatur = json.dumps(stand, sort_keys=True)
        if signatur == self._signatur and (self.ordner / "data.js").exists():
            return False
        daten = json.dumps(stand, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")
        _atomar(self.ordner / "data.js", f"window.__kiosk&&window.__kiosk({daten});\n")
        self._signatur = signatur
        return True


def verkaeufe(ordner: Path | None, tag: date | None = None) -> dict | None:
    """Tageszahlen aus sales/JJJJ-MM-TT.jsonl fuer den Herzschlag."""
    if ordner is None:
        return None
    tag = tag or date.today()
    datei = ordner / "sales" / f"{tag.isoformat()}.jsonl"
    summe = {"count": 0, "photos": 0, "amount_cents": 0, "by_method": {}, "last_at": None}
    try:
        zeilen = datei.read_text(encoding="utf-8").splitlines()
    except OSError:
        return summe
    for zeile in zeilen:
        try:
            v = json.loads(zeile)
        except ValueError:
            continue
        if not isinstance(v, dict):
            continue
        betrag = int(v.get("amount_cents") or 0)
        methode = str(v.get("method") or "other")[:12]
        summe["count"] += 1
        summe["photos"] += len(v.get("items") or [])
        summe["amount_cents"] += betrag
        m = summe["by_method"].setdefault(methode, {"count": 0, "amount_cents": 0})
        m["count"] += 1
        m["amount_cents"] += betrag
        summe["last_at"] = v.get("at") or summe["last_at"]
    return summe


def letzte_verkaeufe(ordner: Path | None, seit: float, jetzt: float | None = None) -> list[dict]:
    """Verkaeufe seit `seit` (Unix-Zeit), fuer die Freischaltung der Download-Codes."""
    if ordner is None:
        return []
    jetzt = time.time() if jetzt is None else jetzt
    tage = {date.fromtimestamp(seit), date.fromtimestamp(jetzt)}
    raus: list[dict] = []
    for tag in sorted(tage):
        try:
            zeilen = (ordner / "sales" / f"{tag.isoformat()}.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for zeile in zeilen:
            try:
                v = json.loads(zeile)
                at = datetime.fromisoformat(str(v.get("at"))).timestamp()
            except (ValueError, TypeError, AttributeError):
                continue
            if at < seit:
                continue
            codes = [str(i.get("code")) for i in v.get("items") or [] if isinstance(i, dict) and i.get("code")]
            raus.append({
                "id": str(v.get("id") or "")[:40],
                "at": v.get("at"),
                "method": str(v.get("method") or "other")[:12],
                "amount_cents": int(v.get("amount_cents") or 0),
                "codes": codes[:50],
                "formats": [str(i.get("format")) for i in v.get("items") or [] if isinstance(i, dict)][:50],
            })
    return raus[-200:]
