"""QR-Ziel und QR-Verkauf des Verkaufsprogramms aus dem CRM umstellen (Roadmap W5).

Der Auftrag reist ueber denselben, abgesicherten Weg wie Neustart und Testfoto
(`settings.pending_restart` mit `target="qr"`). Er traegt hoechstens zwei Werte:

- ``url``: neues ``QrCodeBeginningString`` - der Anfang des Links, den der
  Ausdruck als QR-Code traegt (z. B. ``https://liftpictures-fotos.de/imst/claim?code=``).
- ``enabled``: ``EnableQrCodePrintButtons`` an oder aus - ob der Automat den
  Druck mit QR-Code ueberhaupt anbietet.

Regeln, die das sicher machen
-----------------------------
- **Kein Pfad vom Server.** Welche Settings.xml gemeint ist, steht in der
  Konfiguration DIESES PCs (`viewer_settings_xml`).
- **Nur erlaubte Ziele.** Die URL muss https sein und auf
  ``liftpictures-fotos.de`` (oder eine Unterdomain) zeigen. Alles andere wird
  abgelehnt - ein kompromittierter Server kann Gaeste also nicht auf eine
  fremde Seite schicken.
- **Nur diese zwei Felder.** Es wird gezielt der Text zwischen den Tags ersetzt,
  der Rest der Datei bleibt Byte fuer Byte gleich (Kodierung, Zeilenenden).
- **Vorher Sicherung.** ``Settings.xml.bak-qr-<Zeit>`` neben der Datei.
- **Kein stilles Anlegen.** Fehlt ein Tag, wird nichts erfunden: Ablehnung mit Grund.

Damit die Aenderung wirkt, muss das Verkaufsprogramm neu starten; das erledigt
der Aufrufer (sofort oder in der Ruhezeit), nicht dieses Modul.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

ERLAUBTE_DOMAIN = "liftpictures-fotos.de"
URL_TAG = "QrCodeBeginningString"
SCHALTER_TAG = "EnableQrCodePrintButtons"


@dataclass(frozen=True)
class QrErgebnis:
    ok: bool
    changed: bool
    reason: str
    old_url: str | None = None
    new_url: str | None = None
    old_enabled: bool | None = None
    new_enabled: bool | None = None


def url_erlaubt(url: str) -> bool:
    """https, Host liftpictures-fotos.de oder Unterdomain, keine Zugangsdaten, kein Port."""
    try:
        teile = urlsplit(url.strip())
    except ValueError:
        return False
    host = (teile.hostname or "").lower()
    if teile.scheme != "https" or teile.username or teile.password or teile.port:
        return False
    if any(c in url for c in "<>\"'\r\n\t "):
        return False
    return host == ERLAUBTE_DOMAIN or host.endswith("." + ERLAUBTE_DOMAIN)


def _tag(text: str, tag: str) -> re.Match[str] | None:
    return re.search(rf"<{tag}>([^<]*)</{tag}>", text)


def _als_bool(wert: str | None) -> bool | None:
    if wert is None:
        return None
    w = wert.strip().lower()
    if w in ("true", "1", "yes"):
        return True
    if w in ("false", "0", "no"):
        return False
    return None


def plane_aenderung(text: str, url: str | None, enabled: bool | None) -> tuple[str, QrErgebnis]:
    """Rechnet die neue Settings.xml aus, ohne etwas zu schreiben (testbar)."""
    if url is None and enabled is None:
        return text, QrErgebnis(False, False, "Auftrag ohne url und ohne enabled")
    if url is not None and not url_erlaubt(url):
        return text, QrErgebnis(False, False, f"URL nicht erlaubt (nur https://{ERLAUBTE_DOMAIN}/...)")

    neu = text
    alt_url = alt_an = None
    m_url = _tag(text, URL_TAG)
    m_an = _tag(text, SCHALTER_TAG)
    if m_url:
        alt_url = m_url.group(1)
    if m_an:
        alt_an = _als_bool(m_an.group(1))

    if url is not None:
        if not m_url:
            return text, QrErgebnis(False, False, f"<{URL_TAG}> fehlt in der Settings.xml")
        neu = neu[: m_url.start(1)] + url.strip() + neu[m_url.end(1):]
    if enabled is not None:
        m_an = _tag(neu, SCHALTER_TAG)
        if not m_an:
            return text, QrErgebnis(False, False, f"<{SCHALTER_TAG}> fehlt in der Settings.xml")
        wert = "true" if enabled else "false"
        # Schreibweise der Datei beibehalten (True/true)
        if m_an.group(1)[:1].isupper():
            wert = wert.capitalize()
        neu = neu[: m_an.start(1)] + wert + neu[m_an.end(1):]

    return neu, QrErgebnis(
        True, neu != text, "geaendert" if neu != text else "stand schon so",
        old_url=alt_url, new_url=url.strip() if url is not None else alt_url,
        old_enabled=alt_an, new_enabled=enabled if enabled is not None else alt_an,
    )


def apply_qr(settings_xml: Path | None, url: str | None, enabled: bool | None, now: datetime | None = None) -> QrErgebnis:
    """Settings.xml mit Sicherung aendern. Liest und schreibt binaer, damit Kodierung und Zeilenenden bleiben."""
    if settings_xml is None:
        return QrErgebnis(False, False, "VIEWER_SETTINGS_XML ist auf diesem PC nicht gesetzt")
    if not settings_xml.is_file():
        return QrErgebnis(False, False, f"Settings.xml nicht gefunden: {settings_xml}")
    roh = settings_xml.read_bytes()
    kodierung = "utf-8-sig" if roh.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        text = roh.decode(kodierung)
    except UnicodeDecodeError:
        kodierung = "cp1252"
        text = roh.decode(kodierung)
    neu, ergebnis = plane_aenderung(text, url, enabled)
    if not ergebnis.ok or not ergebnis.changed:
        return ergebnis
    stempel = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    sicherung = settings_xml.with_name(f"{settings_xml.name}.bak-qr-{stempel}")
    sicherung.write_bytes(roh)
    tmp = settings_xml.with_name(settings_xml.name + ".tmp-qr")
    tmp.write_bytes(neu.encode(kodierung))
    tmp.replace(settings_xml)
    log.warning("QR geaendert: %s -> %s, an: %s -> %s (Sicherung %s)",
                ergebnis.old_url, ergebnis.new_url, ergebnis.old_enabled, ergebnis.new_enabled, sicherung.name)
    return ergebnis
