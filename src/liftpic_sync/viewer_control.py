"""Restarting kiosk programs on request from the dashboard.

Why this exists
---------------
Some assets only take effect after a restart. `hintergrund.png` is the clear
case: the viewer opens it once at startup and keeps the handle open, so
`AssetSyncWorker` cannot even replace the file while the viewer runs - the
atomic rename fails on a locked target.

The same lever helps elsewhere. The camera program (3GerTis) writes
`Device lost` when the camera drops off the network and, with
`restart_if_lost=0`, never reconnects on its own: it keeps running and looks
perfectly healthy while taking no pictures at all. Until now that cost a trip to
the machine. A restart from the dashboard fixes it in seconds.

Rules that make this safe
-------------------------
- **The server never names a path, only a key.** Which executable that key
  stands for is decided here, from this PC's own configuration. A compromised or
  mistaken server can therefore not start an arbitrary program.
- **Nothing is restartable unless it was configured.** A PC without the new
  settings behaves exactly as before.
- Processes are matched on their full image path, never on a name, so a
  similarly named program elsewhere is never touched.
- A `tonight` request waits for the quiet window instead of interrupting a sale.
- The process is asked to close politely first and only killed if it refuses.
- Afterwards it is verified that the program actually came back, and the
  outcome is reported honestly.

Deliberately NOT restartable
----------------------------
- **The uploader itself.** It is this very process. Nothing on the machine would
  start it again - not autostart, not a service - so it would leave the kiosk
  unmonitored and out of reach.
- **The print spooler.** Stopping a Windows service needs administrator rights
  the agent does not have; the button would fail every time.
- **Coin validator and card terminal.** Devices, not programs. There is no
  process to restart.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, time as clock_time
from pathlib import Path

from .config import Settings


log = logging.getLogger(__name__)

# How long to wait for the viewer to close on its own before killing it.
GRACEFUL_SECONDS = 10.0
# Pause between stopping and starting, so file handles are really released.
RESTART_PAUSE_SECONDS = 3.0
# Wie lange nach dem Start auf das Erscheinen gewartet wird.
START_WARTEN_SEKUNDEN = 20.0

# Woran man im Kameraprotokoll sieht, ob die Kamera wirklich am Programm haengt.
#
# 3GerTis liest beim Verbinden die Grenzwerte AUS DER KAMERA aus und schreibt sie
# mit dem Zusatz "(from cam)". Kommen diese Zeilen, war die Kamera erreichbar -
# im Gegensatz zu "(from ini)", das nur die eigene Konfigurationsdatei
# wiedergibt und auch ohne Kamera erscheint.
KAMERA_VERBUNDEN_RE = re.compile(r"\(from cam\)", re.IGNORECASE)
KAMERA_VERLOREN_RE = re.compile(r"device lost|geraet verloren|gerät verloren", re.IGNORECASE)

# Wie lange die Kamera nach einem Neustart braucht, bis sie wieder da ist.
# Am 15.08.2026 gemessen: Neustart 11:32:27, verbunden 11:38:55 - also gut
# sechseinhalb Minuten. Ein Testfoto 76 Sekunden nach dem Neustart lief deshalb
# ins Leere, obwohl beides in Ordnung war.
KAMERA_ANLAUF_MINUTEN = 8


@dataclass(frozen=True)
class RestartOutcome:
    performed: bool
    reason: str


@dataclass(frozen=True)
class Programm:
    """Ein Programm, das sich neu starten laesst."""
    key: str
    name: str          # Klarname fuer den Betreiber
    tech: str          # wie es auf dem PC heisst
    exe: Path
    # Was ein Neustart fuer den Gast bedeutet - steht so im Dashboard, damit
    # niemand blind auf einen Knopf drueckt.
    folge: str


def laeuft_ohne_bildschirm() -> bool:
    """Laeuft dieser Prozess in Sitzung 0, also ohne Zugriff auf den Bildschirm?

    Der Installer richtet den Autostart als **SYSTEM**-Aufgabe ein. Windows
    fuehrt die in Sitzung 0 aus, die seit Vista strikt vom Desktop getrennt ist.
    Ein von dort gestartetes Verkaufsprogramm laeuft zwar, ist fuer den Gast
    aber **unsichtbar** - ein "Neustart" wuerde also das sichtbare Programm
    beenden und ein unsichtbares hochfahren. Der Automat waere praktisch aus,
    ohne dass irgendwo ein Fehler stuende.

    Am Testrechner faellt das nicht auf, weil der Agent dort von Hand als
    angemeldeter Benutzer laeuft. Deshalb wird hier gemessen statt angenommen.

    Im Zweifel wird `False` gemeldet: kann die Sitzung nicht bestimmt werden,
    soll die Funktion nicht grundlos verschwinden. Der Schutz greift nur, wenn
    Sitzung 0 sicher feststeht.
    """
    try:
        import ctypes

        eigene = ctypes.c_ulong()
        kernel32 = ctypes.windll.kernel32
        if not kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(),
                                             ctypes.byref(eigene)):
            return False
        return eigene.value == 0
    except Exception:  # kein Windows, keine API - dann keine Aussage
        return False


def restartable_programs(settings: Settings) -> list[Programm]:
    """Welche Programme dieser PC neu starten kann.

    Nur was konfiguriert UND vorhanden ist. Der Agent meldet diese Liste im
    Heartbeat, damit das Dashboard Knoepfe genau dort zeigt, wo sie auch wirken -
    statt zu raten und dem Betreiber einen Knopf hinzustellen, der ins Leere
    greift.
    """
    if not settings.viewer_restart_enabled:
        return []

    # Ohne Bildschirmzugriff waere ein Neustart schaedlich statt hilfreich:
    # das sichtbare Programm ginge aus, das neue niemand zu Gesicht bekaeme.
    if laeuft_ohne_bildschirm():
        log.info(
            "restart targets hidden: this agent runs in session 0 (system service), "
            "a restarted program would be invisible to the guest"
        )
        return []

    kandidaten = (
        ("viewer", "Verkaufsprogramm", "PhotoViewer", settings.viewer_exe,
         "Für etwa 20 Sekunden kann kein Foto verkauft werden."),
        ("camera", "Kamera-Software", "3GerTis", settings.camera_exe,
         "Während des Neustarts entsteht kurz kein Foto. Behebt eine "
         "abgerissene Verbindung zur Kamera."),
        ("lightbarrier", "Lichtschranke", "AidaTest", settings.lightbarrier_exe,
         "Für ein paar Sekunden werden vorbeifahrende Gäste nicht erkannt."),
    )

    gefunden: list[Programm] = []
    for key, name, tech, exe, folge in kandidaten:
        if exe is None:
            continue
        if not exe.exists():
            log.info("restart target '%s' configured but not found: %s", key, exe)
            continue
        gefunden.append(Programm(key=key, name=name, tech=tech, exe=exe, folge=folge))
    return gefunden


def find_program(settings: Settings, key: str) -> Programm | None:
    """Den Schluessel des Servers in ein Programm DIESES PCs uebersetzen.

    Der einzige Weg vom Auftrag zum Prozess. Ein unbekannter Schluessel ergibt
    None und damit einen abgelehnten Auftrag - der Server kann keinen Pfad
    vorgeben.
    """
    gesucht = (key or "viewer").strip().lower()
    for programm in restartable_programs(settings):
        if programm.key == gesucht:
            return programm
    return None


def _parse_clock(value: str, fallback: clock_time) -> clock_time:
    try:
        hours, minutes = value.strip().split(":", 1)
        return clock_time(int(hours), int(minutes))
    except (ValueError, AttributeError):
        return fallback


def in_night_window(settings: Settings, now: datetime | None = None) -> bool:
    """True while the kiosk is expected to be closed.

    The window normally wraps midnight (23:30 -> 05:00), so a plain `start <=
    now <= end` comparison would never match. Both orientations are handled.
    """
    current = (now or datetime.now()).time()
    start = _parse_clock(settings.viewer_night_start, clock_time(23, 30))
    end = _parse_clock(settings.viewer_night_end, clock_time(5, 0))
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def _ausgabe(befehl: list[str], timeout: float = 30.0) -> str:
    """Ein Programm aufrufen und seine Ausgabe holen - ohne je zu scheitern.

    Bewusst NICHT mit ``text=True``: der Agent laeuft ohne Konsole (per
    ``Start-Process -WindowStyle Hidden``), und unter dieser Bedingung kann
    ``tasklist.exe`` gar keine Ausgabe liefern - ``stdout`` ist dann ``None``.
    Genau daran ist ein Neustart abgebrochen, nachdem das Verkaufsprogramm
    bereits beendet war: die Pruefung "laeuft es noch?" warf einen TypeError,
    und der Start danach kam nie zustande.

    Ausserdem ist die Ausgabe auf einem deutschen Windows weder UTF-8 noch die
    Kodierung, die Python annimmt - ``text=True`` stirbt am ersten Umlaut.
    Deshalb Bytes lesen und selbst dekodieren, wie in `system_probe`.
    """
    try:
        fertig = subprocess.run(
            befehl,
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("restart helper %s failed: %s", befehl[0], exc)
        return ""

    roh = fertig.stdout or b""
    for kodierung in ("utf-8", "cp1252", "latin-1"):
        try:
            return roh.decode(kodierung)
        except UnicodeDecodeError:
            continue
    return roh.decode("utf-8", errors="replace")


def _running_pids(exe: Path) -> list[int]:
    """PIDs of processes started from exactly this executable.

    Matched on the full image path rather than the process name so a similarly
    named program elsewhere on the PC is never touched.

    Wichtig (F-044): Windows verweigert `ExecutablePath`, wenn der Prozess einem
    anderen Konto gehoert oder hoeher laeuft als wir - das Feld ist dann LEER,
    nicht falsch. Die alte Fassung filterte solche Prozesse mit
    `Where-Object { $_.ExecutablePath }` einfach weg und hielt ein laufendes
    Verkaufsprogramm fuer tot. Der Neustart startete daraufhin eine zweite
    Instanz, die sich als Einzelinstanz sofort wieder beendete (Exitcode 0),
    und die Kontrolle fand erneut nichts: "ist nicht wieder hochgekommen",
    obwohl es die ganze Zeit lief.

    Deshalb wird der Name jetzt mitgelesen und als Rueckfall benutzt - aber nur
    dort, wo der Pfad nachweislich nicht lesbar ist. Wo ein Pfad da ist, bleibt
    er allein massgeblich.
    """
    target = os.path.normcase(str(exe.resolve(strict=False)))
    name_ziel = os.path.normcase(exe.name)
    ausgabe = _ausgabe([
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-CimInstance Win32_Process | "
        "ForEach-Object { \"$($_.ProcessId)|$($_.Name)|$($_.ExecutablePath)\" }",
    ])

    pids: list[int] = []
    verdeckt: list[int] = []
    for line in ausgabe.splitlines():
        teile = line.split("|", 2)
        if len(teile) < 2:
            continue
        pid_text, name = teile[0], teile[1]
        path = teile[2] if len(teile) > 2 else ""
        try:
            pid = int(pid_text.strip())
        except ValueError:
            continue

        if path.strip():
            if os.path.normcase(path.strip()) == target:
                pids.append(pid)
        elif os.path.normcase(name.strip()) == name_ziel:
            # Gleicher Dateiname, Pfad nicht lesbar. Wir koennen nicht beweisen,
            # dass es unser Programm ist - aber der Irrtum in die andere
            # Richtung ist teurer: er startet eine zweite Instanz und meldet
            # anschliessend faelschlich einen Fehlschlag.
            verdeckt.append(pid)

    if verdeckt and not pids:
        log.warning(
            "%s: %d Prozess(e) mit passendem Namen, aber ohne lesbaren Pfad "
            "(%s) - vermutlich laeuft es unter einem anderen Konto oder hoeher "
            "als wir. Sie werden als laufend gewertet.",
            exe.name, len(verdeckt), ", ".join(str(p) for p in verdeckt),
        )
    return pids + verdeckt


def _stop(pids: list[int]) -> None:
    """Ask politely, then insist."""
    for pid in pids:
        _ausgabe(["taskkill.exe", "/PID", str(pid)], timeout=20)

    deadline = time.time() + GRACEFUL_SECONDS
    while time.time() < deadline:
        time.sleep(1.0)
        if not any(_pid_alive(pid) for pid in pids):
            return

    for pid in pids:
        if _pid_alive(pid):
            log.warning("viewer restart: pid %s did not close, forcing", pid)
            _ausgabe(["taskkill.exe", "/PID", str(pid), "/F"], timeout=20)


def _pid_alive(pid: int) -> bool:
    """Laeuft dieser Prozess noch?

    Kann die Frage nicht beantwortet werden, gilt der Prozess als beendet: der
    Ablauf geht dann weiter und startet das Programm neu. Andersherum - im
    Zweifel "laeuft noch" - bliebe das Programm fuer immer aus, und genau das
    ist passiert, als hier ein Fehler flog: beendet, aber nie wieder gestartet.
    """
    ausgabe = _ausgabe(["tasklist.exe", "/FI", f"PID eq {pid}", "/NH"], timeout=20)
    return str(pid) in ausgabe


def stop_program(settings: Settings, key: str = "viewer") -> RestartOutcome:
    """Ein konfiguriertes Programm anhalten, ohne es wieder zu starten. Wirft nie.

    Bewusst getrennt von `restart_program`, statt dort einen Schalter
    einzubauen: die beiden haben gegensaetzliche Erfolgsbedingungen. Ein
    Neustart ist gelungen, wenn das Programm danach LAEUFT - ein Anhalten,
    wenn es danach WEG ist. In einer Funktion mit `if neustart:` waere frueher
    oder spaeter die falsche Bedingung geprueft worden.

    Wichtig fuer den Aufrufer: nichts startet dieses Programm nach. Keines der
    hier steuerbaren Programme steht in einem Autostart. Wer anhaelt, haelt bis
    jemand es wieder startet - von Hand am Automaten oder ueber den
    Neustart-Knopf.
    """
    if not settings.viewer_restart_enabled:
        return RestartOutcome(False, "Steuerung ist auf diesem PC nicht freigeschaltet")

    programm = find_program(settings, key)
    if programm is None:
        return RestartOutcome(
            False, f"Unbekanntes oder nicht eingerichtetes Ziel: {key!r}"
        )
    exe = programm.exe

    try:
        pids = _running_pids(exe)
    except Exception:
        log.exception("stop %s: could not check", programm.key)
        return RestartOutcome(False, f"{programm.name}: Nachsehen war nicht moeglich")

    if not pids:
        # Kein Fehler. Wer anhalten will, will dass es weg ist - und das ist es.
        log.info("stop %s: was not running", programm.key)
        return RestartOutcome(True, f"{programm.name} lief bereits nicht")

    log.warning("stop %s: stopping %s", programm.key, ", ".join(str(p) for p in pids))
    try:
        _stop(pids)
    except Exception:
        log.exception("stop %s: stopping failed", programm.key)
        return RestartOutcome(False, f"{programm.name} konnte nicht beendet werden")

    time.sleep(1.0)
    try:
        uebrig = _running_pids(exe)
    except Exception:
        log.exception("stop %s: could not verify", programm.key)
        return RestartOutcome(True, f"{programm.name} beendet, Kontrolle war nicht moeglich")

    if uebrig:
        # Der haeufigste Grund: das Programm laeuft erhoeht und wir nicht.
        # Das ehrlich sagen, statt Erfolg zu behaupten (F-044).
        return RestartOutcome(
            False,
            f"{programm.name} laeuft weiter (PID {', '.join(str(p) for p in uebrig)}) - "
            "vermutlich mit hoeheren Rechten als der Agent",
        )

    log.info("stop %s: done", programm.key)
    return RestartOutcome(True, f"{programm.name} beendet")


def restart_program(settings: Settings, key: str = "viewer") -> RestartOutcome:
    """Ein konfiguriertes Programm anhalten und neu starten. Wirft nie.

    `key` kommt vom Server, der Pfad ausschliesslich aus dieser Konfiguration.
    """
    if not settings.viewer_restart_enabled:
        return RestartOutcome(False, "Neustart ist auf diesem PC nicht freigeschaltet")

    programm = find_program(settings, key)
    if programm is None:
        return RestartOutcome(
            False, f"Unbekanntes oder nicht eingerichtetes Ziel: {key!r}"
        )
    exe = programm.exe

    # Anhalten und Starten sind bewusst GETRENNT abgesichert.
    #
    # Beim ersten Einsatz ist genau das schiefgegangen: das Verkaufsprogramm war
    # bereits beendet, dann warf die Kontrolle "laeuft es noch?" einen Fehler -
    # und der gemeinsame try-Block sprang ueber den Start hinweg. Der Automat
    # stand danach ohne Verkaufsprogramm da. Was auch immer beim Anhalten
    # schiefgeht: der Start muss trotzdem versucht werden.
    try:
        pids = _running_pids(exe)
        if pids:
            log.info("restart %s: stopping %s", programm.key,
                     ", ".join(str(p) for p in pids))
            _stop(pids)
        else:
            log.info("restart %s: was not running, starting it", programm.key)
    except Exception:
        log.exception("restart %s: stopping failed, starting anyway", programm.key)

    time.sleep(RESTART_PAUSE_SECONDS)

    try:
        subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            close_fds=True,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    except Exception as exc:
        log.exception("restart %s: could not start %s", programm.key, exe)
        return RestartOutcome(False, f"{programm.name} konnte nicht gestartet werden: {exc}")

    # Nicht einmal nach drei Sekunden schauen, sondern warten, bis es da ist.
    # Ein Programm mit Oberflaeche braucht auf einem Automaten regelmaessig
    # laenger als drei Sekunden; wer nur einmal hinsieht, meldet einen
    # Fehlschlag, der keiner ist. (F-044)
    laeuft = False
    frist = time.time() + START_WARTEN_SEKUNDEN
    try:
        while True:
            if _running_pids(exe):
                laeuft = True
                break
            if time.time() >= frist:
                break
            time.sleep(1.0)
    except Exception:
        # Die Kontrolle ist gescheitert, nicht der Start. Das ehrlich sagen,
        # statt einen Fehlschlag zu behaupten, den es vielleicht nicht gab.
        log.exception("restart %s: could not verify", programm.key)
        return RestartOutcome(
            True, f"{programm.name} gestartet, Kontrolle war nicht möglich",
        )

    if laeuft:
        log.info("restart %s: done", programm.key)
        return RestartOutcome(True, f"{programm.name} neu gestartet")
    # Ehrlich melden statt Erfolg zu behaupten: keines dieser Programme
    # steht im Autostart, es startet also niemand nach.
    return RestartOutcome(False, f"{programm.name} ist nicht wieder hochgekommen")


def restart_viewer(settings: Settings) -> RestartOutcome:
    """Rueckwaertskompatibler Name fuer den Viewer-Neustart."""
    return restart_program(settings, "viewer")


# Wie lange auf das Bild gewartet wird. Die Lichtschranke gibt der Kette rund
# 1,3 Sekunden (AidaTest.ini, CheckTime); mit Aufnahme, Einbrennen und Ablegen
# ist nach 20 Sekunden alles passiert, was passieren wird.
FOTO_WARTEN_SEKUNDEN = 20.0


def _neueste_datei(ordner: Path | None) -> float:
    """Zeitstempel der neuesten Bilddatei, 0 wenn es keine gibt."""
    if ordner is None or not ordner.is_dir():
        return 0.0
    neueste = 0.0
    try:
        for eintrag in ordner.iterdir():
            if eintrag.suffix.lower() in (".jpg", ".jpeg"):
                neueste = max(neueste, eintrag.stat().st_mtime)
    except OSError:
        return 0.0
    return neueste


def _kameraprotokoll(settings: Settings) -> Path | None:
    """Die Protokolldatei der Kamera-Software, neben ihrem Programm."""
    exe = settings.camera_exe
    if exe is None:
        return None
    ordner = exe.parent
    bevorzugt = ordner / "3gerlog.txt"
    if bevorzugt.exists():
        return bevorzugt
    try:
        kandidaten = [p for p in ordner.glob("*.txt") if p.is_file()]
    except OSError:
        return None
    if not kandidaten:
        return None
    return max(kandidaten, key=lambda p: p.stat().st_mtime)


def kamera_ist_verbunden(settings: Settings) -> tuple[bool | None, float | None]:
    """Haengt die Kamera gerade am Programm? Und seit wann steht es so?

    Rueckgabe `(zustand, minuten_her)`. `None` heisst "nicht feststellbar" - kein
    Protokoll gefunden, kein Vermerk darin. Das ist ausdruecklich nicht dasselbe
    wie "nicht verbunden": ohne Anhaltspunkt wird nichts behauptet und der
    Auslöser laeuft wie bisher.

    Gelesen wird von hinten, die juengste Aussage gewinnt. Ein "Device lost" von
    heute frueh sagt nichts mehr, wenn danach wieder "(from cam)" kam.
    """
    protokoll = _kameraprotokoll(settings)
    if protokoll is None:
        return None, None
    try:
        zeilen = protokoll.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None, None

    for zeile in reversed(zeilen[-400:]):
        verbunden = bool(KAMERA_VERBUNDEN_RE.search(zeile))
        verloren = bool(KAMERA_VERLOREN_RE.search(zeile))
        if not (verbunden or verloren):
            continue
        alter = None
        zeitpunkt = _zeit_aus_zeile(zeile)
        if zeitpunkt is not None:
            alter = max(0.0, (datetime.now() - zeitpunkt).total_seconds() / 60.0)
        return verbunden, alter
    return None, None


def _zeit_aus_zeile(zeile: str) -> datetime | None:
    """Der Zeitstempel am Zeilenanfang, im Format der Kamera-Software."""
    treffer = re.match(r"\s*(\d{2}\.\d{2}\.\d{4})[ \t]+(\d{2}:\d{2}:\d{2})", zeile)
    if not treffer:
        return None
    try:
        return datetime.strptime(f"{treffer.group(1)} {treffer.group(2)}", "%d.%m.%Y %H:%M:%S")
    except ValueError:
        return None


def trigger_test_photo(settings: Settings) -> RestartOutcome:
    """Ein Testfoto ausloesen - denselben Weg wie die Lichtschranke.

    Der springende Punkt: **dem Exitcode ist nicht zu trauen.** Am Testrechner
    lieferte `3GerImage.exe` Exitcode 0, obwohl die Kamera seit Tagen weg war -
    kein Bild, nicht einmal ein Eintrag im Kameraprotokoll. Ein Erfolg zaehlt
    deshalb nur, wenn danach wirklich eine neue Bilddatei daliegt.
    """
    exe = settings.test_photo_exe
    if exe is None:
        return RestartOutcome(False, "Testfoto ist auf diesem PC nicht eingerichtet")
    if laeuft_ohne_bildschirm():
        return RestartOutcome(
            False,
            "Der Automat läuft als Systemdienst ohne Bildschirmzugriff - "
            "ein Auslöser von hier erreicht die Kamera-Software nicht.",
        )
    if not exe.exists():
        return RestartOutcome(False, f"Auslöseprogramm nicht gefunden: {exe}")

    # Erst nachsehen, ob die Kamera ueberhaupt am Programm haengt. Sonst wartet
    # man eine halbe Minute auf eine Antwort, die vorher schon feststand - und
    # bekommt am Ende "Kamera hat nicht reagiert", ohne zu erfahren, warum.
    verbunden, seit_minuten = kamera_ist_verbunden(settings)
    if verbunden is False:
        if seit_minuten is not None and seit_minuten < KAMERA_ANLAUF_MINUTEN:
            return RestartOutcome(
                False,
                "Die Kamera-Software wurde gerade neu gestartet und hat die "
                f"Kamera noch nicht gefunden (seit {int(seit_minuten)} min). "
                f"Das dauert bis zu {KAMERA_ANLAUF_MINUTEN} Minuten - danach "
                "noch einmal auslösen.",
            )
        return RestartOutcome(
            False,
            "Die Kamera ist nicht mit der Kamera-Software verbunden. Ein "
            "Testfoto kann so nicht entstehen. Zuerst die Kamera-Software neu "
            "starten und einige Minuten warten, bis sie wieder verbunden ist.",
        )

    vorher_roh = _neueste_datei(settings.raw_dir)
    vorher_fertig = _neueste_datei(settings.qrcode_dir or settings.processed_dir)

    try:
        subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            close_fds=True,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    except Exception as exc:
        log.exception("test photo: could not start %s", exe)
        return RestartOutcome(False, f"Auslösen fehlgeschlagen: {exc}")

    # Warten, bis eine neue Datei auftaucht - lieber frueh aufhoeren als stur
    # die volle Zeit stehen.
    frist = time.time() + FOTO_WARTEN_SEKUNDEN
    while time.time() < frist:
        time.sleep(1.0)
        if _neueste_datei(settings.raw_dir) > vorher_roh:
            break
        if _neueste_datei(settings.qrcode_dir or settings.processed_dir) > vorher_fertig:
            break

    neu_roh = _neueste_datei(settings.raw_dir) > vorher_roh
    neu_fertig = _neueste_datei(settings.qrcode_dir or settings.processed_dir) > vorher_fertig

    if neu_fertig:
        return RestartOutcome(True, "Testfoto aufgenommen und fertig verarbeitet")
    if neu_roh:
        # Die Kamera hat ausgeloest, aber die Lichtschranken-Software hat das
        # Bild nicht gestempelt - sie sieht nur nach, wenn SIE ausgeloest hat.
        # Also selbst hochladen, gekennzeichnet als Testfoto.
        return RestartOutcome(True, "Testfoto aufgenommen")
    return RestartOutcome(
        False,
        "Kein Bild entstanden. Der Auslöser lief durch, die Kamera hat aber "
        "nicht reagiert - meist ist sie nicht erreichbar (siehe Kamera-Software).",
    )
