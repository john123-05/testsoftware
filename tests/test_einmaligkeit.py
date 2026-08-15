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


# ------------------------------------------------- Anspruch auf Uploads

def _foto(store, event_key: str) -> None:
    from liftpic_sync.state import PhotoEvent

    store.upsert_event(PhotoEvent(
        capture_id=event_key,
        raw_path=None,
        processed_path=f"C:/liftpic/fotos/qrcode/{event_key}.jpg",
        legacy_filename=f"{event_key}.jpg",
        captured_at="2026-08-15T10:00:00",
        speed_kmh=None,
        speed_status="missing",
        upload_status="queued",
        checksum="x",
        event_key=event_key,
    ), metadata={})


def test_zwei_agenten_greifen_nicht_dasselbe_foto(tmp_path: Path):
    """Der Kern von F-025.

    Frueher war `due_uploads` ein reines SELECT. Zwei Agenten waehlten damit
    garantiert dieselben Zeilen - gleiche Sortierung, gleiches Limit - und
    luden jedes Foto zweimal hoch, weil der Status erst nach dem fertigen
    Upload wechselte.
    """
    from liftpic_sync.state import StateStore

    db = tmp_path / "state.db"
    a = StateStore(db)
    b = StateStore(db)
    try:
        for i in range(3):
            _foto(a, f"foto-{i}")

        erste = list(a.due_uploads())
        zweite = list(b.due_uploads())

        assert len(erste) == 3, "der erste Agent bekommt alles"
        assert zweite == [], "der zweite darf nichts davon sehen"
        # Und es steht dran, wer sie hat.
        assert all(r["upload_status"] == "uploading" for r in
                   a.conn.execute("SELECT upload_status FROM photo_events"))
    finally:
        a.close()
        b.close()


def test_abgestuerzter_upload_wird_wieder_frei(tmp_path: Path):
    """Ein Absturz mitten im Upload darf die Zeile nicht fuer immer blockieren.

    Deshalb eine Verfallszeit statt eines Kennzeichens, das niemand mehr
    zuruecksetzt.
    """
    from liftpic_sync.state import StateStore

    store = StateStore(tmp_path / "state.db")
    try:
        _foto(store, "foto-1")
        assert len(list(store.due_uploads())) == 1
        assert list(store.due_uploads()) == [], "solange der Anspruch gilt: gesperrt"

        # Den Anspruch kuenstlich altern lassen.
        store.conn.execute(
            "UPDATE photo_events SET claimed_at = claimed_at - ?",
            (StateStore.ANSPRUCH_GILT_SEKUNDEN + 60,),
        )
        store.conn.commit()

        assert len(list(store.due_uploads())) == 1, "nach Ablauf wieder faellig"
    finally:
        store.close()


def test_fehlversuch_gibt_den_anspruch_zurueck(tmp_path: Path):
    """Nach einem Fehlschlag muss die Zeile wieder aufgreifbar sein - sonst
    wartet sie unnoetig bis zum Ablauf der Verfallszeit."""
    from liftpic_sync.state import StateStore

    store = StateStore(tmp_path / "state.db")
    try:
        _foto(store, "foto-1")
        list(store.due_uploads())
        store.mark_retry("foto-1", "Netz weg", retry_after=0)

        zeile = store.conn.execute(
            "SELECT upload_status, claimed_by, claimed_at FROM photo_events"
        ).fetchone()

        assert zeile["upload_status"] == "retry"
        assert zeile["claimed_by"] is None
        assert zeile["claimed_at"] is None
        assert len(list(store.due_uploads())) == 1
    finally:
        store.close()


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
