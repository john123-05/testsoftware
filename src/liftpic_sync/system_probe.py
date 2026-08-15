"""Measuring the machine directly, instead of inferring it from log files.

Log files answer "what did this program last say?". They cannot answer "is it
running right now?" - a program that crashed hard writes nothing at all, and its
last line still reads perfectly healthy. The whole tool then silently
disappears from the health page at exactly the moment it matters.

These probes ask the machine itself: which programs are alive, does the payment
terminal answer, is the printer ready, are the serial ports there, how is the PC
doing. Each probe is independent and fails soft - one that cannot answer returns
"unknown" rather than raising, because a broken probe must never cost us the
heartbeat that carries the others.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings


log = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PS = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"]


@dataclass
class Probe:
    """One measured fact about the machine."""
    key: str
    name: str
    kind: str
    status: str          # ok | warn | down | off | unknown
    detail: str
    value: object = None
    since_minutes: int | None = None
    tech: str = ""
    # Wofuer das Ding da ist, in einem Satz. Ein Betreiber sieht "Anschluesse:
    # COM2, COM4 vorhanden" und weiss ohne diesen Satz nicht, ob ihn das
    # betreffen sollte.
    purpose: str = ""
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "detail": self.detail,
            "value": self.value,
            "since_minutes": self.since_minutes,
            "tech": self.tech,
            "purpose": self.purpose,
            **({"extra": self.extra} if self.extra else {}),
        }


def _run_ps(script: str, timeout: float = 20.0) -> str | None:
    """Run a PowerShell one-liner and return its stdout.

    Reads bytes and decodes explicitly: Windows console output on a German
    system is neither UTF-8 nor the codepage Python assumes, and `text=True`
    dies on the first umlaut - which is exactly what `w32tm` prints. Decoding
    ourselves with a fallback keeps a probe alive instead of losing it to a
    character.
    """
    try:
        done = subprocess.run(
            _PS + [script],
            capture_output=True, timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("probe command failed: %s", exc)
        return None

    raw = done.stdout or b""
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------- processes

def probe_processes(watched: list[tuple[str, str, str, str]]) -> list[Probe]:
    """Which of the kiosk programs are actually running.

    `watched` is (process name, plain name, technical name, purpose). Matched on
    the process name because that is what Windows reports; the exe path can
    differ between installs.
    """
    out = _run_ps(
        "Get-Process | Select-Object Name,Id,StartTime | "
        "ForEach-Object { \"$($_.Name)|$($_.Id)|$($_.StartTime)\" }"
    )
    running: dict[str, tuple[int, str]] = {}
    if out:
        for line in out.splitlines():
            parts = line.split("|")
            if len(parts) >= 3 and parts[0].strip():
                running[parts[0].strip().lower()] = (
                    int(parts[1]) if parts[1].strip().isdigit() else 0,
                    parts[2].strip(),
                )

    probes: list[Probe] = []
    for proc_name, display, tech, purpose in watched:
        # Alternatives share one device identity; the key stays on the first
        # name so the history does not split when a site switches programs.
        alternatives = [item.strip() for item in proc_name.split("|") if item.strip()]
        key = f"proc:{alternatives[0]}" if alternatives else f"proc:{proc_name}"
        hit = None
        gefunden = ""
        for candidate in alternatives:
            hit = running.get(candidate.lower())
            if hit:
                gefunden = candidate
                break
        # Steht ein anderes als das erstgenannte Programm dahinter, dann gehoert
        # dessen Name in die Klammer - sonst behauptet die Seite "3GerTis",
        # waehrend in Wahrheit TIScapture arbeitet.
        tech_aktuell = PROGRAM_TECH.get(gefunden.lower(), tech) if gefunden else tech

        if out is None:
            probes.append(Probe(
                key=key, name=display, kind="process", status="unknown",
                detail="Konnte nicht geprueft werden", tech=tech, purpose=purpose,
            ))
            continue
        if hit:
            minutes = _minutes_since_local(hit[1])
            probes.append(Probe(
                key=key, name=display, kind="process", status="ok",
                detail=(
                    f"Laeuft seit {_human(minutes)}" if minutes is not None else "Laeuft"
                ),
                value=hit[0], since_minutes=minutes, tech=tech_aktuell,
                purpose=purpose,
            ))
        else:
            # Not running is not automatically a fault - a kiosk outside opening
            # hours is supposed to be off. The dashboard decides how to read it.
            probes.append(Probe(
                key=key, name=display, kind="process", status="off",
                detail="Nicht gestartet", tech=tech, purpose=purpose,
            ))
    return probes


# Prozessname -> Produktname. Nur noetig, wo mehrere Programme dieselbe Aufgabe
# erfuellen koennen und die Klammer zeigen soll, welches es gerade ist.
PROGRAM_TECH = {
    "3gertis_v70": "3GerTis",
    "camera26": "TIScapture",
}


def _minutes_since_local(stamp: str) -> int | None:
    for fmt in ("%d.%m.%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            started = datetime.strptime(stamp.strip(), fmt)
            return max(0, int((datetime.now() - started).total_seconds() / 60))
        except ValueError:
            continue
    return None


# ----------------------------------------------------------------- terminal

def probe_tcp(host: str, port: int, name: str, tech: str) -> Probe:
    """Does something answer on this address - the payment terminal, typically.

    A plain TCP connect, no protocol talk: we only want to know whether the box
    is powered and on the network. Deliberately not a ping, because ICMP is
    commonly blocked while the port itself answers fine.
    """
    key = f"tcp:{host}:{port}"
    if not host:
        return Probe(key=key, name=name, kind="terminal", status="unknown",
                     detail="Keine Adresse hinterlegt", tech=tech)
    started = time.time()
    try:
        with socket.create_connection((host, port), timeout=4.0):
            ms = int((time.time() - started) * 1000)
            return Probe(key=key, name=name, kind="terminal", status="ok",
                         detail=f"Antwortet in {ms} ms", value=ms, tech=tech)
    except (OSError, socket.timeout) as exc:
        return Probe(key=key, name=name, kind="terminal", status="down",
                     detail=f"Keine Antwort von {host}:{port}",
                     tech=tech, extra={"error": str(exc)[:200]})


# ------------------------------------------------------------------ printer

def probe_printers() -> list[Probe]:
    out = _run_ps(
        "Get-Printer | ForEach-Object { "
        "$j = @(Get-PrintJob -PrinterName $_.Name -ErrorAction SilentlyContinue).Count; "
        "\"$($_.Name)|$($_.PrinterStatus)|$j\" }"
    )
    if not out:
        return [Probe(key="printer", name="Drucker", kind="printer", status="unknown",
                      detail="Konnte nicht geprueft werden", tech="Windows-Druckerdienst")]

    probes: list[Probe] = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3 or not parts[0]:
            continue
        name, state, jobs = parts[0], parts[1], parts[2]
        # Virtual printers say nothing about the photo output. "Print to PDF"
        # gehoert dazu: sonst meldet ein PC ganz ohne Fotodrucker ein
        # zufriedenes "Drucker bereit", waehrend nichts gedruckt werden kann.
        if re.search(r"(xps|fax|onenote|print to pdf|pdf-?drucker)", name, re.IGNORECASE):
            continue
        queued = int(jobs) if jobs.isdigit() else 0
        ok = state.lower() in ("normal", "idle", "0", "3")
        probes.append(Probe(
            key=f"printer:{name}", name="Drucker", kind="printer",
            status="ok" if ok else "warn",
            detail=(
                f"Bereit, {queued} Auftraege in der Warteschlange" if ok
                else f"Meldet '{state}'"
            ),
            value=queued, tech=name,
        ))
    if not probes:
        probes.append(Probe(key="printer", name="Drucker", kind="printer", status="off",
                            detail="Kein Fotodrucker eingerichtet", tech="Windows-Druckerdienst"))
    return probes


# --------------------------------------------------------------- serial/COM

def probe_serial(expected: list[str]) -> Probe:
    """Are the serial ports the light barrier needs present at all?

    A missing COM port means the light barrier cannot trigger - that is a
    hardware fault the log would only reveal indirectly, as silence.
    """
    out = _run_ps("[System.IO.Ports.SerialPort]::GetPortNames() -join ','")
    if out is None:
        return Probe(key="serial", name="Anschlüsse", kind="system", status="unknown",
                     detail="Konnte nicht geprueft werden", tech="COM-Schnittstellen")
    ports = [p.strip().upper() for p in out.strip().split(",") if p.strip()]
    missing = [p for p in expected if p.upper() not in ports]
    # Kategorie "system", damit die Zeile in der einfachen Ansicht nur dann
    # auftaucht, wenn tatsaechlich ein Anschluss fehlt. Dass COM2 und COM4 da
    # sind, muss niemand taeglich lesen - dass einer fehlt, sehr wohl.
    if not expected:
        return Probe(key="serial", name="Anschlüsse", kind="system", status="ok",
                     detail=f"Vorhanden: {', '.join(ports) or 'keine'}",
                     value=ports, tech="COM-Schnittstellen")
    if missing:
        return Probe(key="serial", name="Anschlüsse", kind="system", status="down",
                     detail=f"Fehlt: {', '.join(missing)} (vorhanden: {', '.join(ports) or 'keine'})",
                     value=ports, tech="COM-Schnittstellen")
    return Probe(key="serial", name="Anschlüsse", kind="system", status="ok",
                 detail=f"{', '.join(expected)} vorhanden", value=ports,
                 tech="COM-Schnittstellen")


# ------------------------------------------------------------------- system

def probe_system(settings: Settings) -> list[Probe]:
    probes: list[Probe] = []

    try:
        usage = shutil.disk_usage(settings.app_dir.anchor or "C:\\")
        free_gb = usage.free / 1024 ** 3
        total_gb = usage.total / 1024 ** 3
        pct = (usage.free / usage.total) * 100 if usage.total else 0
        probes.append(Probe(
            key="disk", name="Speicherplatz", kind="system",
            status="ok" if pct > 10 else "warn" if pct > 4 else "down",
            detail=f"{free_gb:.0f} von {total_gb:.0f} GB frei",
            value=round(free_gb, 1), tech="Festplatte",
        ))
    except OSError:
        pass

    out = _run_ps(
        "$o = Get-CimInstance Win32_OperatingSystem; "
        "\"$($o.FreePhysicalMemory)|$($o.TotalVisibleMemorySize)|$($o.LastBootUpTime)\""
    )
    if out and "|" in out:
        parts = out.strip().splitlines()[0].split("|")
        try:
            free_mb = float(parts[0]) / 1024
            total_mb = float(parts[1]) / 1024
            pct = (free_mb / total_mb) * 100 if total_mb else 0
            probes.append(Probe(
                key="memory", name="Arbeitsspeicher", kind="system",
                status="ok" if pct > 12 else "warn",
                detail=f"{free_mb / 1024:.1f} von {total_mb / 1024:.0f} GB frei",
                value=round(free_mb / 1024, 1), tech="RAM",
            ))
        except (ValueError, IndexError, ZeroDivisionError):
            pass
        if len(parts) > 2:
            minutes = _minutes_since_local(parts[2])
            if minutes is not None:
                probes.append(Probe(
                    key="uptime", name="PC-Laufzeit", kind="system", status="ok",
                    detail=f"Seit {_human(minutes)} in Betrieb",
                    value=minutes, since_minutes=minutes, tech="Windows",
                ))

    return probes


# --------------------------------------------------------------------- time

def probe_clock() -> Probe:
    """Is the PC clock in sync?

    Worth its own probe: the claim code contains the capture DATE. A PC whose
    clock has slipped past midnight prints codes for the wrong day, and every
    one of those photos becomes unclaimable - while every log looks perfectly
    normal. A silent, expensive failure.
    """
    out = _run_ps("w32tm /query /status")
    if not out:
        return Probe(key="clock", name="Uhrzeit", kind="system", status="unknown",
                     detail="Zeitabgleich nicht abfragbar", tech="Windows-Zeitdienst")
    text = out.lower()
    if "not been synchronized" in text or "nicht synchronisiert" in text:
        return Probe(key="clock", name="Uhrzeit", kind="system", status="warn",
                     detail="PC-Uhr ist nicht synchronisiert - das kann Foto-Codes verschieben",
                     tech="Windows-Zeitdienst")
    source = ""
    for line in out.splitlines():
        if re.match(r"\s*(source|quelle)\s*:", line, re.IGNORECASE):
            source = line.split(":", 1)[1].strip()
            break
    return Probe(key="clock", name="Uhrzeit", kind="system", status="ok",
                 detail=f"Abgeglichen mit {source}" if source else "Abgeglichen",
                 tech="Windows-Zeitdienst")


# -------------------------------------------------------------------- driver

def _human(minutes: int | None) -> str:
    if minutes is None:
        return "unbekannt"
    if minutes < 90:
        return f"{minutes} Min."
    hours = minutes / 60
    if hours < 48:
        return f"{hours:.1f} Std."
    return f"{hours / 24:.1f} Tagen"


# Kiosk programs worth watching: (process name, display name, technical hint).
#
# The process name may list alternatives separated by "|". Some jobs are done by
# different programs depending on how old the installation is - the camera is
# driven either by 3GerTis (older, calls the GigE camera through The Imaging
# Source libraries) or by TIScapture/camera26 (newer). Both fill the same role,
# so they are one device here. Listing them separately would report "Kamera
# ausgefallen" on every machine that happens to use the other program.
DEFAULT_PROCESSES: list[tuple[str, str, str, str]] = [
    ("PhotoViewerFacebook!", "Verkaufsprogramm", "PhotoViewer",
     "Bildschirm am Automaten: Fotos, Zahlung, Druck."),
    ("AidaTest", "Lichtschranke", "AidaTest",
     "Erkennt Gäste und löst die Kamera aus."),
    ("3gerTis_v70|camera26", "Kamera-Software", "3GerTis",
     "Nimmt das Foto auf."),
]


# Wofuer jede Messung steht, in einem Satz fuer den Betreiber. Zentral gepflegt
# statt an jedem einzelnen Probe-Aufruf: so steht der ganze erklaerende Text an
# einer Stelle und laesst sich lesen wie ein Inhaltsverzeichnis der Anlage.
# Schluessel ist der Anfang des Probe-Keys; Prozesse bringen ihren Satz selbst
# mit, weil er dort direkt neben dem Programmnamen steht.
PROBE_PURPOSE: tuple[tuple[str, str], ...] = (
    ("tcp:", "Bezahlterminal für EC und Kreditkarte."),
    ("printer", "Gibt die gekauften Bilder aus."),
    ("serial", "Steckplätze für Lichtschranke und Münzprüfer."),
    ("disk", "Freier Speicher für neue Fotos."),
    ("memory", "Arbeitsspeicher des PCs."),
    ("uptime", "Laufzeit seit dem letzten Neustart."),
    ("clock", "Steht im Abholcode jedes Fotos - geht sie falsch, "
              "finden Gäste ihre Bilder nicht."),
)


def _purpose_for(key: str) -> str:
    for prefix, text in PROBE_PURPOSE:
        if key.startswith(prefix):
            return text
    return ""


def collect_probes(settings: Settings) -> list[dict]:
    """Run every probe. Never raises - a failing probe becomes 'unknown'."""
    probes: list[Probe] = []

    def guard(fn, *args):
        try:
            result = fn(*args)
            probes.extend(result if isinstance(result, list) else [result])
        except Exception as exc:  # a probe must never break the heartbeat
            log.debug("probe %s failed: %s", getattr(fn, "__name__", fn), exc)

    guard(probe_processes, DEFAULT_PROCESSES)
    if settings.terminal_host:
        guard(probe_tcp, settings.terminal_host, settings.terminal_port,
              "Kartenterminal", "ZVT")
    guard(probe_printers)
    guard(probe_serial, list(settings.expected_com_ports))
    guard(probe_system, settings)
    guard(probe_clock)

    for probe in probes:
        if not probe.purpose:
            probe.purpose = _purpose_for(probe.key)

    return [p.as_dict() for p in probes]
