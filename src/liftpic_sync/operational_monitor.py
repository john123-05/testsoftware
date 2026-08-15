"""Reading the machine's own log files to report what is actually working.

The kiosk PC runs a handful of independent programs, each writing its own log:
the sales viewer, the coin validator, the speed/light-barrier tool, the camera
capture, the payment terminal - plus this agent. None of them report health
anywhere; the only trace they leave is a line in a text file.

This module tails those files and turns them into a per-tool status. Two
principles matter:

1. **One entry per tool, not per category.** Earlier every file was squeezed
   into one of five buckets (cash/terminal/printer/camera/system) by guessing
   from keywords, and only the worst finding per bucket survived. A log the
   keywords did not match vanished entirely - which is why the health page kept
   showing nothing. Sources are now recognised by their known path, so each tool
   appears under its own name and a match is never a coincidence.

2. **Silence is a state, not an error.** A tool that has not written for hours
   is reported as `idle` with its last activity, rather than either raising a
   false alarm from a stale line or disappearing from the list. Only genuinely
   dead files (older than `defunct`) are dropped.
"""
from __future__ import annotations

import glob
import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings


@dataclass(frozen=True)
class OperationalDevice:
    name: str
    kind: str
    status: str
    detail: str
    source_file: str
    last_seen_at: str | None
    severity: str
    # Der technische Name, den ein Techniker kennt (PhotoViewer, 3GerTis, ZVT).
    # Bewusst getrennt vom Klarnamen: der Betreiber liest "Kamera-Software", der
    # Techniker braucht daneben "3GerTis". Beides in EIN Feld zu schreiben macht
    # die Kachel unlesbar und laesst sich im Dashboard nicht mehr trennen.
    tech: str = ""
    # Welche Eintraege zu einem Geraet verschmelzen. Bei bekannten Quellen ist
    # das Kategorie+Klarname, damit die drei Protokolle des Verkaufsprogramms
    # eine Kachel ergeben. Bei unbekannten Protokollen gehoert die Technik in
    # den Schluessel - sonst wuerden zwei fremde Dateien derselben Kategorie
    # einander verdraengen und eine davon verschwaende spurlos.
    merge_key: str = ""
    # Wofuer das Geraet da ist, in einem Satz fuer den Betreiber.
    purpose: str = ""
    # Klartext-Uebersetzung der Meldung, getrennt vom Rohtext in `detail`.
    # Beides zusammengeklebt hiess: eingeklappt liest man Erklaerung UND
    # Rohtext, aufgeklappt den Rohtext noch einmal. Getrennt kann die Seite
    # eingeklappt die Erklaerung zeigen und den Rohtext erst beim Aufklappen.
    plain: str = ""
    # Minutes since the file was last written. Lets the dashboard say "quiet for
    # 3 h" instead of only showing a bare status word.
    idle_minutes: int | None = None
    # True, wenn die Meldung aus dem EIGENEN Protokoll des Geraets stammt.
    # Eine Fremderwaehnung (das Verkaufsprogramm schreibt ueber den Muenzpruefer)
    # darf den Befund aus der Originalquelle nie ueberstimmen - die kennt den
    # vollen Verlauf des Geraets, die Fremderwaehnung nur einen Satz daraus.
    primary: bool = True


@dataclass(frozen=True)
class OperationalStatus:
    devices: list[OperationalDevice]
    events: list[dict[str, object]]
    coin_status: str | None
    terminal_status: str | None
    printer_status: str | None
    camera_status: str | None


PROBLEM_RE = re.compile(
    r"(critical|fatal|panic|error|fehler|failed|failure|offline|disabled|"
    # "Device lost" ist die Zeile, mit der sich die GigE-Kamera verabschiedet.
    # Sie traegt keinen Protokoll-Rang und enthaelt keines der ueblichen
    # Reizwoerter, wurde deshalb als harmlos eingestuft - die Kachel blieb gruen,
    # waehrend die Kamera tot war. Genau dieser Ausfall blieb einmal vier Tage
    # unbemerkt. 3GerTis laeuft mit restart_if_lost=0 und verbindet sich nicht
    # von allein neu, es braucht also immer einen Eingriff.
    r"device lost|geraet verloren|gerät verloren|"
    r"communication lost|can't connect|cannot connect|not connected|no response|"
    r"timeout|paper empty|printer offline|coinchangererror|validator.*error|"
    r"exception|abgebrochen|verweigert|nicht gefunden|konnte nicht)",
    re.IGNORECASE,
)
WARNING_RE = re.compile(
    r"(warn|warning|paper low|low paper|retry|blocked|stoerung|störung|"
    r"kontrollieren|uebersprungen|übersprungen)",
    re.IGNORECASE,
)
OK_RE = re.compile(
    r"(ready|bereit|ok\b|connected|enabled|success|successful|image triggered|"
    r"state:\s*(wait|blocking)|terminal bereit|status - ready|hochgeladen|"
    # Die Entwarnung der Kamera. 3GerTis liest beim Verbinden die Grenzwerte
    # AUS DER KAMERA und schreibt sie mit "(from cam)"; "(from ini)" stammt aus
    # der eigenen Konfigurationsdatei und erscheint auch ohne Kamera - deshalb
    # steht hier ausdruecklich nur "cam". Dazu die gespeicherte Bilddatei, die
    # ebenso beweist, dass die Kamera arbeitet.
    #
    # Ohne diese Marker gab es fuer die Kamera ueberhaupt keine Entwarnung: seit
    # "Device lost" als Stoerung gilt, blieb sie am 15.08.2026 auch dann rot,
    # als sie um 11:38:55 laengst wieder verbunden war.
    r"\(from cam\)|image has been saved|"
    r"start application|programmstart)",
    re.IGNORECASE,
)
TIMESTAMP_RE = re.compile(
    r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{4})\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2})(?:[.,](?P<millis>\d{1,3}))?"
)
ISO_TIMESTAMP_RE = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[ T]"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
)

# Structured logs (this agent, anything using Python logging) carry an explicit
# level. Trusting it beats keyword guessing: the agent's own status line reads
# "... 'failed': 0 ...", which the keyword matcher would happily report as a
# failure although it states the exact opposite.
LEVEL_RE = re.compile(
    r"^\s*\S+[ T]\S+\s+(?P<level>CRITICAL|ERROR|WARNING|WARN|INFO|DEBUG)\b"
)
# Counters that explicitly report zero problems ("failed=0", "'failed': 0").
# Stripped before keyword matching so they cannot trigger a false alarm.
ZERO_COUNTER_RE = re.compile(
    r"['\"]?(failed|failures|errors?|fehler)['\"]?\s*[:=]\s*0\b",
    re.IGNORECASE,
)


def _level_from_line(line: str) -> str | None:
    """Severity taken from an explicit log level, if the line carries one."""
    match = LEVEL_RE.match(line)
    if not match:
        return None
    level = match.group("level").upper()
    if level in ("CRITICAL", "ERROR"):
        return "error"
    if level in ("WARNING", "WARN"):
        return "warning"
    return "info"

# Known log sources: (filename fragment, plain name, category, technical name).
# Matched against the file name first, then the parent folder, so a renamed or
# rotated file (NRI.CoinCharger_082026.txt) is still recognised.
#
# The plain name is what the park operator reads; the technical name is what a
# technician needs on the phone. Several files may share a plain name on
# purpose - the sales program writes three logs, and three tiles for one program
# is noise, not information. They are merged into one entry further down.
KNOWN_SOURCES: tuple[tuple[str, str, str, str], ...] = (
    ("nri.coincharger", "Münzprüfer", "cash", "NRI CoinCharger"),
    ("coinstats", "Münzeinnahmen", "cash", "CoinStats"),
    ("zvtlog", "Kartenterminal", "terminal", "ZVT"),
    ("zvt-", "Kartenterminal", "terminal", "ZVT"),
    ("easyzvt", "Kartenterminal", "terminal", "EasyZVT"),
    ("checkingtool", "Kartenterminal-Prüfung", "terminal", "CheckingTool"),
    ("aidatest", "Lichtschranke", "camera", "AidaTest"),
    ("speedshot", "Lichtschranke", "camera", "Speedshot"),
    ("camera_capture", "Kamera-Software", "camera", "TIScapture"),
    ("3gerlog", "Kamera-Software", "camera", "3GerTis"),
    ("errors.log", "Verkaufsprogramm", "viewer", "PhotoViewer, Fehlerprotokoll"),
    ("debug.log", "Verkaufsprogramm", "viewer", "PhotoViewer, Ablaufprotokoll"),
    ("watchdog.log", "Verkaufsprogramm", "viewer", "PhotoViewer, Überwachung"),
    ("liftpic-sync", "Uploader", "uploader", "liftpic-sync"),
    ("printsettings", "Drucker", "printer", "PrintSettings"),
)

# Marker the agent puts on lines that merely relay another tool's message.
# Without filtering these back out, reading our own log would turn every relayed
# warning into a fresh warning about the warning - a feedback loop that grows
# with each scan.
RELAY_MARKER = "[geraet]"

# Eine Meldung gehoert zu dem Geraet, von dem sie HANDELT - nicht zu der Datei,
# in der sie steht. Das Verkaufsprogramm protokolliert den Münzprüfer in seinem
# eigenen debug.log; ohne diese Zuordnung meldet die Seite "Verkaufsprogramm
# ausgefallen", obwohl das Programm laeuft und nur der Muenzpruefer klemmt.
CONTENT_OWNER: tuple[tuple[str, str, str, str], ...] = (
    # Die Code-Vorschrift zuerst: dass Automat und Verkaufsprogramm
    # verschiedene Kundennummern hinterlegt haben, ist kein Fehler des
    # Uploaders - er bemerkt es nur beim Start und sagt es laut. Ohne diese
    # Zuordnung faerbt diese eine Startmeldung den Uploader dauerhaft gelb,
    # obwohl er einwandfrei arbeitet.
    (r"customer number differs|codepositionsinfilename|kundennummer",
     "Abholcode", "config", "Settings.xml"),
    # Der E-Mail-Versand: die Meldung "Error sending statistic
    # email" enthaelt oft auch Geraetewoerter, gehoert aber eindeutig zum
    # Berichtsversand und nicht zum Geraet.
    (r"sending .*email|statistic email|smtp|mailserver|e-?mail",
     "Statistik-E-Mail", "mail", "Tagesbericht per E-Mail"),
    # Die Internetpruefung des Verkaufsprogramms (es loest www.google.com auf).
    # Schlaegt sie fehl, ist die Leitung schuld, nicht das Programm - sonst
    # steht "Verkaufsprogramm ausgefallen" wegen eines DNS-Aussetzers.
    (r"internetconnection|remotename konnte nicht|could not be resolved|"
     r"no such host|namensaufl",
     "Internetverbindung", "network", "Netzwerk"),
    (r"coin\s*changer|coinchanger|münzprüfer|muenzpruefer|nri\.",
     "Münzprüfer", "cash", "NRI CoinCharger"),
    (r"\bzvt\b|kartenterminal|kreditkarte|girocard|ec-cash",
     "Kartenterminal", "terminal", "ZVT"),
    (r"printer|drucker|paper|papier", "Drucker", "printer", "Windows-Drucker"),
)

# Nebenfunktionen: Dinge, die schiefgehen koennen, ohne dass der Automat
# aufhoert zu verkaufen. Ein Fehler hier ist eine Warnung, kein Ausfall - sonst
# faerbt sich die Anlage rot, weil ein Bericht nicht verschickt wurde.
SIDE_FUNCTIONS = {"mail"}

# Technische Meldungen in einen Satz uebersetzen, den der Betreiber versteht.
# Ohne das steht auf der Seite "System.Security.Authentication.Authentication-
# Exception: Fehler bei SSPI-Aufruf" - eine Zeile, mit der niemand ausserhalb
# der Entwicklung etwas anfangen kann.
PLAIN_EXPLANATION: tuple[tuple[str, str], ...] = (
    (r"customer number differs",
     "Automat und Verkaufsprogramm haben verschiedene Kundennummern "
     "hinterlegt. Der Automat übernimmt die gedruckte - die Codes stimmen, "
     "aber die Einstellungen sollten angeglichen werden."),
    (r"internetconnection|remotename konnte nicht|could not be resolved",
     "Der Automat hatte zeitweise keine Internetverbindung."),
    (r"sspi|authenticationexception|ssl|tls|schannel",
     "Verschlüsselung wird nicht akzeptiert - Windows-Verfahren zu alt."),
    (r"device lost|geraet verloren",
     "Kamera nicht mehr erreichbar. Verbindet sich nicht von allein neu."),
    (r"coin\s*changer\s*error|coinchangererror",
     "Münzprüfer antwortet nicht."),
    (r"paper\s*(empty|out)|papier\s*leer", "Kein Papier mehr im Drucker."),
    (r"paper\s*low|wenig papier", "Druckerpapier geht zur Neige."),
    (r"timeout|zeitüberschreitung|zeitueberschreitung",
     "Keine Antwort in der erwarteten Zeit."),
    (r"no response|keine antwort|not connected|nicht verbunden",
     "Gerät meldet sich nicht."),
    (r"disk|speicherplatz|festplatte voll", "Speicherplatz wird knapp."),
)


# Wofuer jedes Geraet da ist - derselbe Gedanke wie PROBE_PURPOSE im
# system_probe, hier nach Klarnamen statt nach Messschluessel.
DEVICE_PURPOSE: dict[str, str] = {
    "Münzprüfer": "Nimmt Münzen an und gibt Wechselgeld.",
    "Münzeinnahmen": "Tagesabrechnung der Münzkasse.",
    "Kartenterminal": "Bezahlterminal für EC und Kreditkarte.",
    "Kartenterminal-Prüfung": "Prüft, ob das Terminal antwortet.",
    "Lichtschranke": "Erkennt Gäste und löst die Kamera aus.",
    "Kamera-Software": "Nimmt das Foto auf.",
    "Verkaufsprogramm": "Bildschirm am Automaten: Fotos, Zahlung, Druck.",
    "Uploader": "Lädt die Fotos zu Liftpictures hoch.",
    "Drucker": "Gibt die gekauften Bilder aus.",
    "Statistik-E-Mail": "Täglicher Umsatzbericht. Nebenfunktion.",
    "Abholcode": "Legt fest, welche Nummer auf den Beleg gedruckt wird.",
    "Internetverbindung": "Nötig für Upload und Kartenzahlung.",
}


def _plain_explanation(text: str) -> str:
    """Ein Satz Klartext zu einer technischen Meldung, sonst leer."""
    for pattern, erklaerung in PLAIN_EXPLANATION:
        if re.search(pattern, text, re.IGNORECASE):
            return erklaerung
    return ""

# Ein Geraet, das nie in Betrieb war, ist nicht ausgefallen - es ist nicht
# angeschlossen. Diese Zeilen belegen echten Betrieb; fehlen sie voellig,
# waehrend es Fehler gibt, hat das Geraet nie gearbeitet.
OPERATION_RE = re.compile(
    # Auch eine reine Bereitschaftsmeldung zaehlt: wer "ready" meldet, ist
    # angeschlossen und antwortet - dann ist ein spaeterer Fehler ein echter
    # Ausfall und nicht ein fehlendes Geraet.
    r"(ready|bereit|accepted|inserted|credit|auszahlung|einwurf|payout|dispense|"
    r"vend|autorisierung|zahlung erfolgreich|betrag|transaktion)",
    re.IGNORECASE,
)

# Stacktrace-Zeilen sagen nichts darueber, WAS kaputt ist - sie zeigen nur, wo
# im fremden Code es passierte. Als Meldung im Dashboard sind sie wertlos.
STACKTRACE_RE = re.compile(r"^\s*(bei|at)\s+[\w.<>]+\(", re.IGNORECASE)

CATEGORY_FALLBACK_NAME = {
    "cash": "Münzprüfer",
    "terminal": "Kartenterminal",
    "printer": "Drucker",
    "camera": "Kamera / Lichtschranke",
    "viewer": "Verkaufsprogramm",
    "uploader": "Uploader",
    "network": "Internetverbindung",
    "config": "Abholcode",
    "mail": "Statistik-E-Mail",
    "system": "Sonstige Protokolle",
}


def read_operational_status(settings: Settings) -> OperationalStatus:
    devices: dict[str, OperationalDevice] = {}
    events: list[dict[str, object]] = []

    for path in _iter_log_files(settings.operational_log_globs):
        for device in _inspect_log(path, settings):
            # Pro Geraet ein Eintrag. Frueher war der Schluessel die Datei,
            # wodurch derselbe Muenzpruefer zweimal erschien - einmal aus seinem
            # eigenen Protokoll, einmal aus dem debug.log des Verkaufsprogramms,
            # das ihn miterwaehnt. Zwei Kacheln fuer ein Geraet sind fuer
            # niemanden lesbar.
            key = device.merge_key or f"{device.kind}|{device.name}".lower()
            vorhanden = devices.get(key)
            if vorhanden is None:
                devices[key] = device
            elif vorhanden.primary != device.primary:
                # Originalquelle schlaegt Fremderwaehnung, unabhaengig vom Zustand.
                if device.primary:
                    devices[key] = device
            elif _status_priority(device.status) > _status_priority(vorhanden.status):
                devices[key] = device
            if device.severity in ("error", "warning"):
                events.append(_device_event(device))

    ordered = sorted(devices.values(), key=lambda item: (_kind_order(item.kind), item.name))
    return OperationalStatus(
        devices=ordered,
        events=sorted(events, key=lambda item: str(item.get("occurred_at") or ""), reverse=True)[:30],
        coin_status=_status_for(ordered, "cash"),
        terminal_status=_status_for(ordered, "terminal"),
        printer_status=_status_for(ordered, "printer"),
        camera_status=_status_for(ordered, "camera"),
    )


def _kind_order(kind: str) -> int:
    # Reihenfolge nach dem Weg, den ein Foto durchs Haus nimmt. Nebenfunktionen
    # (mail) stehen hinten, weil sie den Verkauf nicht aufhalten.
    order = ["camera", "viewer", "cash", "terminal", "printer", "uploader",
             "network", "config", "mail", "system"]
    return order.index(kind) if kind in order else len(order)


# Wo zusaetzlich selbst gesucht wird, wenn die Muster nichts hergeben.
#
# Die konfigurierten Muster sind eine Vorgabe, keine Wahrheit: sie stammen von
# einem PC, auf dem alles am erwarteten Ort lag. Auf einem Automaten mit anderen
# Ordnernamen fanden sie nichts, und die Seite blieb leer - ohne dass irgendwo
# stand, dass gar nicht gesucht wurde (F-030).
# Dateinamen, die zu haeufig sind, um allein etwas zu beweisen.
GENERISCHE_NAMEN = {"errors.log", "debug.log", "watchdog.log"}

# Ordner, die nachweislich einem ANDEREN Geraet gehoeren. Liegt eine Datei mit
# generischem Namen dort, gehoert sie diesem Programm - nicht dem
# Verkaufsprogramm. Der Ordner des Verkaufsprogramms steht hier bewusst nicht.
FREMDE_ORDNER = {
    "3gertis", "camware", "tiscapture", "kosel", "terminal", "imageloader",
    "liftpic-sync", "jpeg4web", "dist", "log", "logs",
}

SUCH_TIEFE = 3
LOG_ENDUNGEN = {".log", ".txt"}
# Ordner, in denen nichts Protokollartiges liegt und die gross werden koennen.
SUCH_AUSNAHMEN = {
    "fotos", "out", "webout", "qrcode", "backups", "state", ".venv",
    "__pycache__", ".git", "node_modules", "buttons", "sounds", "dist",
}


def _such_wurzeln(patterns: tuple[str, ...]) -> list[Path]:
    """Wo gesucht wird - abgeleitet aus den konfigurierten Mustern.

    Bewusst kein fester Pfad: die Muster sagen bereits, wo die Anlage ihre
    Sachen hat. Aus `C:\\liftpic\\3GerTis\\*.log` wird `C:\\liftpic\\3GerTis`
    und dessen Elternordner `C:\\liftpic` - damit findet die Suche auch
    Nachbarordner, die in keinem Muster stehen. Auf einem Automaten mit ganz
    anderem Ablageort wandert die Suche automatisch mit.
    """
    wurzeln: dict[str, Path] = {}
    for pattern in patterns:
        teile: list[str] = []
        for teil in Path(pattern).parts:
            if any(z in teil for z in "*?["):
                break
            teile.append(teil)
        if len(teile) < 2:
            continue
        ordner = Path(*teile)
        for kandidat in (ordner, ordner.parent):
            # Nicht bis zum Laufwerksbuchstaben hochlaufen.
            if len(kandidat.parts) >= 2:
                wurzeln.setdefault(str(kandidat).lower(), kandidat)
    return list(wurzeln.values())


def _selbst_suchen(bereits: dict[str, Path], grenze: int, patterns: tuple[str, ...]) -> None:
    """Unter den abgeleiteten Wurzeln nach Protokolldateien sehen.

    Ergaenzt, was die Muster nicht abgedeckt haben. Bewusst flach (drei Ebenen)
    und ohne die grossen Bilderordner, damit das nicht bei jedem Durchlauf ueber
    zehntausende Fotos laeuft.
    """
    for basis in _such_wurzeln(patterns):
        if not basis.is_dir():
            continue
        for tiefe in range(1, SUCH_TIEFE + 1):
            if len(bereits) >= grenze:
                return
            try:
                kandidaten = basis.glob("/".join(["*"] * tiefe))
            except OSError:
                continue
            for pfad in kandidaten:
                if len(bereits) >= grenze:
                    return
                try:
                    if pfad.suffix.lower() not in LOG_ENDUNGEN or not pfad.is_file():
                        continue
                    if any(teil.lower() in SUCH_AUSNAHMEN for teil in pfad.parts):
                        continue
                    if pfad.stat().st_size == 0:
                        continue
                except OSError:
                    continue
                bereits.setdefault(str(pfad).lower(), pfad)


def _iter_log_files(patterns: tuple[str, ...], grenze: int = 200) -> list[Path]:
    """Alle Protokolldateien, neueste zuerst.

    Erst die konfigurierten Muster, dann die eigene Suche. Die Obergrenze lag
    frueher bei 60 und schnitt nach dem Alter ab - auf einem Automaten mit
    vielen alten Dateien konnten damit die interessanten herausfallen.
    """
    # Was ein Muster trifft, ist beabsichtigt und geht IMMER mit. Was die
    # Selbstsuche findet, fuellt nur auf.
    #
    # Beides in einen Topf zu werfen war ein Fehler: die Suche brachte auf
    # diesem PC 200 Dateien, und weil nach Aenderungsdatum abgeschnitten wurde,
    # fielen aeltere, aber wichtige Protokolle heraus - die Lichtschranke
    # verschwand aus der Anzeige, obwohl sie vorher da war.
    aus_mustern: dict[str, Path] = {}
    for pattern in patterns:
        # `recursive=True`, damit ein `**` im Muster auch wirkt. Ohne das
        # verhielt sich `**` wie ein einfaches `*` - eine stille Falle fuer
        # jeden, der ein Muster von Hand eintraegt.
        for match in glob.glob(pattern, recursive=True):
            path = Path(match)
            if path.is_file():
                aus_mustern[str(path).lower()] = path

    gefunden: dict[str, Path] = dict(aus_mustern)
    _selbst_suchen(gefunden, grenze, patterns)
    nur_gefunden = {k: v for k, v in gefunden.items() if k not in aus_mustern}

    def nach_alter(werte) -> list[Path]:
        return sorted(
            werte,
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )

    ergebnis = nach_alter(aus_mustern.values())[:grenze]
    platz = grenze - len(ergebnis)
    if platz > 0:
        ergebnis.extend(nach_alter(nur_gefunden.values())[:platz])
    return ergebnis


def _identify(path: Path, lines: list[str]) -> tuple[str, str] | None:
    """Map a log file to (display name, category).

    Known paths win, because a match there is intentional rather than a
    coincidence. Anything else falls back to keywords so a log this build has
    never heard of - a customer PC with different tools or file names - still
    shows up instead of silently disappearing. Only files with no health-related
    content at all are dropped.
    """
    name = path.name.lower()
    parent = path.parent.name.lower()
    for fragment, label, kind, tech in KNOWN_SOURCES:
        if fragment in name or fragment in f"{parent}/{name}":
            # Allerweltsnamen brauchen den passenden Ordner (F-030).
            #
            # `errors.log`, `debug.log` und `watchdog.log` heissen bei jedem
            # zweiten Programm so. Eine `debug.log` unter `CAMware\` oder
            # `TIScapture\dist\` - beide in den Mustern - wurde dadurch als
            # "Verkaufsprogramm" gefuehrt und verschmolz per merge_key mit dem
            # echten. Unter der Kachel des Verkaufsprogramms stand dann der
            # Rohtext eines voellig anderen Programms.
            if fragment in GENERISCHE_NAMEN and parent in FREMDE_ORDNER:
                continue
            return label, kind, tech, True

    kind = _guess_kind(path, lines)
    if kind is None:
        # Frueher wurde die Datei hier verworfen (F-030). Ein sauber laufendes,
        # unbekanntes Programm, das nur "Zyklus 4711 beendet" schreibt, war fuer
        # die Seite nicht existent - und niemand konnte sehen, dass es
        # ueberhaupt eine Quelle gibt. Jetzt erscheint es als eigene Quelle,
        # einsortiert unter "system", damit es die Hauptgeraete nicht verdraengt.
        kind = "system"
    # Unbekanntes Protokoll: Klarname aus der Kategorie, Dateiname als Technik.
    # Als "nicht bekannt" markiert, damit es sich nicht mit einem anderen
    # fremden Protokoll derselben Kategorie zusammenlegt.
    return CATEGORY_FALLBACK_NAME.get(kind, "Protokoll"), kind, path.name, False


def _guess_kind(path: Path, lines: list[str]) -> str | None:
    haystack = f"{path} {' '.join(lines[-20:])}".lower()
    if re.search(r"(coin|nri|muenz|münz|cash|barzahlung|coinchanger)", haystack):
        return "cash"
    if re.search(r"(zvt|terminal|kreditkarte|cashless|girocard|ec-cash)", haystack):
        return "terminal"
    if re.search(r"(printer|paper|papier|druck)", haystack):
        return "printer"
    if re.search(r"(aida|speed|camera|kamera|camware|tiscapture|image triggered)", haystack):
        return "camera"
    if re.search(r"(error|fehler|warning|warn|offline|disabled|exception)", haystack):
        return "system"
    return None


def _inspect_log(path: Path, settings: Settings) -> list[OperationalDevice]:
    """Was diese Protokolldatei ueber den Zustand der Anlage sagt.

    Gibt eine LISTE zurueck, weil eine Datei von mehreren Dingen berichten kann:
    das Verkaufsprogramm schreibt auch ueber den Muenzpruefer, der Uploader auch
    ueber den Abholcode. Der Urheber der Datei bleibt dabei immer erhalten.
    """
    try:
        stat = path.stat()
    except OSError:
        return []
    if stat.st_size == 0:
        return []

    now = datetime.now(timezone.utc)
    mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
    age_minutes = (now - mtime).total_seconds() / 60.0

    # Genuinely dead file (rotated away, years old) - not worth reporting.
    if age_minutes > settings.operational_log_defunct_minutes:
        return []

    lines = _tail_lines(path, max(20, settings.operational_log_tail_lines))
    if not lines:
        return []

    identified = _identify(path, lines)
    if identified is None:
        return []
    label, kind, tech, bekannt = identified

    if kind == "uploader":
        # Our own log: drop the lines where we relayed someone else's message,
        # otherwise we would report our own reporting - each scan quoting the
        # previous one, growing without end. Matched on the marker and on the
        # relay wording, so entries written before the marker existed are caught
        # too. Genuine agent problems (failed heartbeat, upload rejected) carry
        # neither and stay visible.
        lines = [
            line for line in lines
            if RELAY_MARKER not in line and " meldet: " not in line
        ]
        if not lines:
            return []

    is_recent = age_minutes <= settings.operational_log_stale_minutes

    if not is_recent:
        # Quiet but not dead. Report it as such instead of guessing - a stale
        # line must never masquerade as a live fault, and the tool must not
        # silently disappear from the list either.
        line_text = _latest_signal_line(lines) or lines[-1]
        return [_baue_geraet(
            label=label, kind=kind, tech=tech, bekannt=bekannt, path=path,
            age_minutes=age_minutes, primary=True,
            line_text=line_text,
            status="idle", severity="info",
            # Nur der Rohtext im Detail. Wie lange es her ist, steht in
            # `idle_minutes` und damit ohnehin schon daneben - beides in
            # denselben Satz zu schreiben hiess, dasselbe zweimal zu lesen.
            plain=f"Seit {_human_minutes(age_minutes)} keine neue Meldung.",
            mtime_iso=mtime.isoformat(),
        )]

    # Eine Datei kann von mehreren Dingen berichten. Das Verkaufsprogramm
    # protokolliert den Muenzpruefer, der Uploader meldet eine abweichende
    # Kundennummer. Solche Zeilen gehoeren dem Geraet, von dem sie HANDELN -
    # aber sie duerfen den Urheber nicht verdraengen: frueher uebernahm die
    # fremde Zuordnung den ganzen Eintrag, und der Uploader verschwand aus der
    # Liste, sobald er einmal etwas ueber etwas anderes schrieb.
    eigene: str | None = None
    fremde: dict[tuple[str, str, str], str] = {}
    for line in _signal_candidates(lines):
        owner = _owner_from_content(line)
        if owner is None or owner[1] == kind:
            if eigene is None:
                eigene = line
        else:
            fremde.setdefault(owner, line)

    # Hat der Urheber gar keine eigene Meldung, darf trotzdem nicht die fremde
    # in seiner Kachel stehen - sonst liest man unter "Verkaufsprogramm" den
    # Fehler des E-Mail-Versands. Dann lieber die neueste wirklich eigene Zeile,
    # und wenn es die nicht gibt, ein ehrliches "nichts vorgefallen".
    eigener_text = ""
    for line in reversed(lines):
        owner = _owner_from_content(line)
        if owner is None or owner[1] == kind:
            eigener_text = line
            break

    geraete: list[OperationalDevice] = [
        _bewerte(
            label=label, kind=kind, tech=tech, bekannt=bekannt, path=path,
            age_minutes=age_minutes, primary=True,
            signal_line=eigene,
            fallback=eigener_text or "Keine eigenen Meldungen im Protokoll.",
            alle_zeilen=lines,
            mtime_iso=mtime.isoformat(),
        )
    ]
    for (fremd_label, fremd_kind, fremd_tech), line in fremde.items():
        geraete.append(_bewerte(
            label=fremd_label, kind=fremd_kind, tech=fremd_tech, bekannt=True,
            path=path, age_minutes=age_minutes, primary=False,
            signal_line=line, fallback=line, alle_zeilen=lines,
            mtime_iso=mtime.isoformat(),
        ))
    return geraete


def _bewerte(
    *, label: str, kind: str, tech: str, bekannt: bool, path: Path,
    age_minutes: float, primary: bool, signal_line: str | None, fallback: str,
    alle_zeilen: list[str], mtime_iso: str,
) -> OperationalDevice:
    """Aus einer Signalzeile einen Geraetezustand machen."""
    line_text = signal_line or fallback
    severity = _classify_line(signal_line) if signal_line else "info"
    status = {"error": "down", "warning": "degraded"}.get(severity, "operational")
    plain = ""

    # Nie in Betrieb gewesen heisst: nicht angeschlossen, nicht ausgefallen.
    # Ein defektes Geraet hinterlaesst Spuren erfolgreicher Vorgaenge, ein
    # fehlendes meldet von Anfang an nur Fehler.
    if status == "down" and kind in ("cash", "terminal") and not _ever_operated(alle_zeilen):
        status, severity = "off", "info"
        plain = "Vermutlich nicht angeschlossen - kein Betrieb feststellbar."

    # Eine kaputte Nebenfunktion ist kein Anlagenausfall. Der Verkauf laeuft
    # weiter, wenn der Tagesbericht nicht rausgeht - rot waere gelogen.
    if status == "down" and kind in SIDE_FUNCTIONS:
        status, severity = "degraded", "warning"

    return _baue_geraet(
        label=label, kind=kind, tech=tech, bekannt=bekannt, path=path,
        age_minutes=age_minutes, primary=primary, line_text=line_text,
        status=status, severity=severity,
        # Klartext getrennt festhalten. `detail` bleibt der Rohtext des
        # Programms - ihn braucht, wer den Hersteller anruft.
        plain=plain or _plain_explanation(line_text),
        mtime_iso=mtime_iso,
    )


def _baue_geraet(
    *, label: str, kind: str, tech: str, bekannt: bool, path: Path,
    age_minutes: float, primary: bool, line_text: str, status: str,
    severity: str, plain: str, mtime_iso: str,
) -> OperationalDevice:
    return OperationalDevice(
        name=label,
        kind=kind,
        status=status,
        detail=line_text.strip()[:240],
        source_file=str(path),
        last_seen_at=_parse_line_time(line_text) or mtime_iso,
        severity=severity,
        idle_minutes=int(age_minutes),
        primary=primary,
        tech=tech,
        merge_key=f"{kind}|{label}".lower() if bekannt else f"{kind}|{label}|{tech}".lower(),
        purpose=DEVICE_PURPOSE.get(label, ""),
        plain=plain,
    )


def _owner_from_content(line: str) -> tuple[str, str, str] | None:
    """Von welchem Geraet handelt diese Zeile, unabhaengig von der Datei."""
    for pattern, label, kind, tech in CONTENT_OWNER:
        if re.search(pattern, line, re.IGNORECASE):
            return label, kind, tech
    return None


def _ever_operated(lines: list[str]) -> bool:
    """Gibt es im sichtbaren Verlauf irgendeinen echten Betriebsvorgang?"""
    return any(OPERATION_RE.search(line) for line in lines)


def _human_minutes(minutes: float) -> str:
    if minutes < 90:
        return f"{int(minutes)} Min."
    hours = minutes / 60.0
    if hours < 48:
        return f"{hours:.1f} Std."
    return f"{hours / 24:.1f} Tagen"


def _tail_lines(path: Path, count: int) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 64_000))
            raw = handle.read()
    except OSError:
        return []
    text = raw.decode("utf-8", errors="replace")
    if text.count("�") > 8:
        text = raw.decode("latin1", errors="replace")
    return [line for line in text.splitlines() if line.strip()][-count:]


def _classify_line(line: str) -> str:
    """Severity of a single log line: 'error', 'warning' or 'info'.

    An explicit log level wins; only lines without one fall back to keywords,
    and those are cleaned of zero-counters first.
    """
    level = _level_from_line(line)
    if level is not None:
        return level

    cleaned = ZERO_COUNTER_RE.sub("", line)
    if PROBLEM_RE.search(cleaned):
        return "error"
    if WARNING_RE.search(cleaned):
        return "warning"
    return "info"


def _signal_candidates(lines: list[str]) -> list[str]:
    """Alle Zeilen, die etwas ueber den Zustand sagen - neueste zuerst.

    Strictly newest-wins, deliberately: a device that reported an error and has
    since reported "ready" has recovered, and must not stay red for ever. The
    lasting record of what happened lives in the buffered health events; this
    value is only the current state.
    """
    out: list[str] = []
    for line in reversed(lines[-40:]):
        if STACKTRACE_RE.match(line):
            continue
        if _classify_line(line) in ("error", "warning") or OK_RE.search(line):
            out.append(line)
    return out


def _latest_signal_line(lines: list[str]) -> str | None:
    """Die neueste aussagekraeftige Zeile, ohne Ruecksicht auf den Urheber."""
    kandidaten = _signal_candidates(lines)
    return kandidaten[0] if kandidaten else None


def _parse_line_time(line: str) -> str | None:
    """Der Zeitpunkt aus einer Protokollzeile, als UTC (F-032).

    Die Programme am Automaten schreiben ORTSZEIT: "15.08.2026 10:11:42" heisst
    zehn nach zehn am Automaten. Frueher wurde diese Zahl mit
    `tzinfo=timezone.utc` gestempelt - aus 10:11 Ortszeit wurde damit 10:11 UTC,
    also 12:11 Ortszeit. Im Verlauf standen alle Ereignisse aus Protokollzeilen
    zwei Stunden in der Zukunft (im Winter eine).

    Harmlos fuer den Betrieb, aber es macht jede Nachforschung unbrauchbar: eine
    Abfrage "was ist in der letzten halben Stunde passiert" zeigte Ereignisse,
    die zwei Stunden alt waren - und verschwieg die echten. Genau darauf sind
    wir am 15.08.2026 hereingefallen.

    Deshalb wird ohne `tzinfo` gebaut - das ist Ortszeit - und mit
    `astimezone` in UTC umgerechnet. Der Sommerzeit-Versatz kommt damit
    automatisch richtig heraus, statt fest angenommen zu werden.
    """
    match = TIMESTAMP_RE.search(line)
    if match:
        parts = {key: int(value) if value else 0 for key, value in match.groupdict().items()}
        try:
            return datetime(
                parts["year"], parts["month"], parts["day"],
                parts["hour"], parts["minute"], parts["second"],
                parts["millis"] * 1000,
            ).astimezone(timezone.utc).isoformat()
        except ValueError:
            return None

    iso = ISO_TIMESTAMP_RE.search(line)
    if iso:
        parts = {key: int(value) for key, value in iso.groupdict().items()}
        try:
            return datetime(
                parts["year"], parts["month"], parts["day"],
                parts["hour"], parts["minute"], parts["second"],
            ).astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
    return None


def _status_priority(status: str) -> int:
    return {"idle": 1, "operational": 2, "degraded": 3, "down": 4}.get(status, 0)


def _status_for(devices: list[OperationalDevice], kind: str) -> str | None:
    relevant = [device for device in devices if device.kind == kind]
    if not relevant:
        return None
    return max(relevant, key=lambda item: _status_priority(item.status)).status


def _device_event(device: OperationalDevice) -> dict[str, object]:
    category = {
        "cash": "cash",
        "terminal": "terminal",
        "printer": "printer",
    }.get(device.kind, "system")
    digest = hashlib.sha1(
        f"{device.source_file}|{device.detail}".encode("utf-8", errors="replace")
    ).hexdigest()[:12]
    return {
        "id": f"agent-{device.kind}-{digest}",
        "occurred_at": device.last_seen_at,
        "severity": device.severity,
        "category": category,
        "payment_method": "coin" if device.kind == "cash" else "terminal" if device.kind == "terminal" else None,
        "status": "failed" if device.status == "down" else "warning" if device.status == "degraded" else "info",
        "amount_cents": None,
        "amount_kind": "unknown",
        "purchase_signal": "none",
        "description": device.detail,
        "source_file": device.source_file,
        "raw_excerpt": device.detail,
        "device": device.name,
        "tags": ["liftpic-agent", device.kind],
    }
