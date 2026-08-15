"""Dass immer nur ein Agent arbeitet - und dass man es nachweisen kann.

Der Hintergrund steht in `docs/FEHLERJOURNAL.md` unter F-024 bis F-026: die
Sperre war seit dem 08.08.2026 wirkungslos, weil die Sperrdatei dem Konto
SYSTEM gehoerte und der Fehlerfall `except OSError: return True` hiess - der
Agent lief ungeschuetzt weiter und sagte niemandem etwas davon.

Die Tests halten die drei Ausgaenge fest und vor allem den Unterschied
zwischen "belegt" (wir beenden uns) und "ungesichert" (wir laufen weiter, aber
laut).
"""
import logging
from pathlib import Path

import pytest

from liftpic_sync.cli import (
    Sperrergebnis, _acquire_single_instance_lock, _sperre_versuchen,
)
from liftpic_sync.logging_setup import configure_logging


def test_erste_instanz_bekommt_die_sperre(tmp_path: Path):
    ergebnis = _acquire_single_instance_lock(tmp_path / "singleton.lock")

    assert ergebnis.gesperrt
    assert ergebnis.handle is not None
    ergebnis.handle.close()


def test_zweite_instanz_wird_abgewiesen(tmp_path: Path):
    """Der Kernfall: der zweite Agent darf nicht danebenlaufen."""
    pfad = tmp_path / "singleton.lock"
    erster = _acquire_single_instance_lock(pfad)
    assert erster.gesperrt

    zweiter = _acquire_single_instance_lock(pfad)

    assert zweiter.belegt
    assert not zweiter.gesperrt
    assert zweiter.handle is None
    erster.handle.close()


def test_sperre_wird_beim_prozessende_frei(tmp_path: Path):
    """Ein Absturz darf keine verwaiste Sperre hinterlassen.

    Das Betriebssystem gibt die Sperre mit dem Schliessen der Datei frei -
    anders als bei einer PID-Datei muss niemand aufraeumen.
    """
    pfad = tmp_path / "singleton.lock"
    erster = _acquire_single_instance_lock(pfad)
    assert erster.gesperrt
    erster.handle.close()  # entspricht dem Prozessende

    danach = _acquire_single_instance_lock(pfad)

    assert danach.gesperrt
    danach.handle.close()


def test_unbeschreibbarer_ort_laesst_den_agenten_weiterlaufen(
    tmp_path: Path, monkeypatch, caplog,
):
    """Ein Rechteproblem darf eine produktive Anlage nie stilllegen.

    Aber der ungeschuetzte Zustand muss laut werden - frueher lief der Agent
    hier stumm weiter, und niemand erfuhr je davon (F-024).
    """
    def scheitert(pfad):
        return f"{pfad}: Zugriff verweigert"

    monkeypatch.setattr("liftpic_sync.cli._sperre_versuchen", scheitert)
    monkeypatch.setattr("liftpic_sync.cli._ausweich_lock_pfad", lambda: None)

    with caplog.at_level(logging.ERROR):
        ergebnis = _acquire_single_instance_lock(tmp_path / "geht-nicht.lock")

    assert ergebnis.ungesichert
    assert not ergebnis.belegt, "ungesichert ist NICHT dasselbe wie belegt"
    assert ergebnis.handle is None
    # Der Grund muss beim Aufrufer ankommen, damit er im Verlauf landet.
    assert "Doppelstart-Schutz nicht aktiv" in ergebnis.grund
    assert any("Doppelstart-Schutz nicht aktiv" in r.message for r in caplog.records)


def test_weicht_auf_den_zweiten_ort_aus(tmp_path: Path, monkeypatch):
    """Ist der systemweite Ort gesperrt, schuetzt der benutzereigene wenigstens
    gegen zwei Agenten desselben Benutzers."""
    ausweich = tmp_path / "lokal" / "singleton.lock"
    echt = _sperre_versuchen

    def nur_der_erste_scheitert(pfad):
        if pfad != ausweich:
            return f"{pfad}: Zugriff verweigert"
        return echt(pfad)

    monkeypatch.setattr("liftpic_sync.cli._sperre_versuchen", nur_der_erste_scheitert)
    monkeypatch.setattr("liftpic_sync.cli._ausweich_lock_pfad", lambda: ausweich)

    ergebnis = _acquire_single_instance_lock(tmp_path / "programdata.lock")

    assert ergebnis.gesperrt
    assert ausweich.exists()
    ergebnis.handle.close()


def test_die_drei_zustaende_schliessen_sich_aus():
    """Damit niemand zwei davon gleichzeitig prueft und danebenliegt."""
    for zustand in ("gesperrt", "belegt", "ungesichert"):
        e = Sperrergebnis(zustand)
        assert [e.gesperrt, e.belegt, e.ungesichert].count(True) == 1


def test_protokoll_nennt_die_prozessnummer(tmp_path: Path):
    """Ohne Prozessnummer ist Doppelbetrieb nicht nachweisbar (F-026).

    In 11 MB Protokoll war kein Verdachtsfall entscheidbar; die Stoerung am
    Imster Automaten wurde deshalb monatelang als "401-Problem" gelesen.
    """
    import os
    from types import SimpleNamespace

    configure_logging(SimpleNamespace(log_dir=tmp_path))
    logging.getLogger("liftpic_sync.test").info("probe")
    for handler in logging.getLogger().handlers:
        handler.flush()

    inhalt = (tmp_path / "liftpic-sync.log").read_text(encoding="utf-8")

    assert f"pid={os.getpid()}" in inhalt
    assert "probe" in inhalt
