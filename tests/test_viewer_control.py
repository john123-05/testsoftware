"""Prozesserkennung fuer Neustarts.

Haelt F-044 fest: Windows verweigert `ExecutablePath`, wenn der Prozess einem
anderen Konto gehoert oder hoeher laeuft. Das Feld ist dann LEER, nicht falsch.
Wer solche Zeilen wegfiltert, haelt ein laufendes Verkaufsprogramm fuer tot,
startet eine zweite Instanz - die sich als Einzelinstanz sofort beendet - und
meldet anschliessend "ist nicht wieder hochgekommen", obwohl es durchlief.
"""

from pathlib import Path

import pytest

from liftpic_sync import viewer_control


EXE = Path(r"C:\liftpic\samuel_neu\PhotoViewerFacebook!.exe")


def _antwort(zeilen, monkeypatch):
    monkeypatch.setattr(viewer_control, "_ausgabe", lambda *a, **k: "\n".join(zeilen))


def test_pfad_treffer_wird_gefunden(monkeypatch):
    _antwort([
        r"111|PhotoViewerFacebook!.exe|C:\liftpic\samuel_neu\PhotoViewerFacebook!.exe",
        r"222|explorer.exe|C:\Windows\explorer.exe",
    ], monkeypatch)
    assert viewer_control._running_pids(EXE) == [111]


def test_leerer_pfad_mit_gleichem_namen_gilt_als_laufend(monkeypatch):
    """Der eigentliche F-044-Fall: Prozess laeuft, Pfad ist nicht lesbar."""
    _antwort([
        r"11584|PhotoViewerFacebook!.exe|",
        r"222|explorer.exe|C:\Windows\explorer.exe",
    ], monkeypatch)
    assert viewer_control._running_pids(EXE) == [11584]


def test_leerer_pfad_mit_fremdem_namen_zaehlt_nicht(monkeypatch):
    """Der Rueckfall darf nicht jeden unlesbaren Prozess einsammeln."""
    _antwort([
        r"333|irgendwas.exe|",
        r"444|System|",
    ], monkeypatch)
    assert viewer_control._running_pids(EXE) == []


def test_gleicher_name_an_anderem_ort_zaehlt_nicht(monkeypatch):
    """Ist der Pfad lesbar, entscheidet allein er - so wie vorher."""
    _antwort([
        r"555|PhotoViewerFacebook!.exe|D:\woanders\PhotoViewerFacebook!.exe",
    ], monkeypatch)
    assert viewer_control._running_pids(EXE) == []


def test_pfad_schlaegt_rueckfall(monkeypatch):
    """Beides da: der Treffer mit Pfad steht vorn, der verdeckte kommt dazu."""
    _antwort([
        r"111|PhotoViewerFacebook!.exe|C:\liftpic\samuel_neu\PhotoViewerFacebook!.exe",
        r"11584|PhotoViewerFacebook!.exe|",
    ], monkeypatch)
    assert viewer_control._running_pids(EXE) == [111, 11584]


def test_kaputte_zeilen_stoeren_nicht(monkeypatch):
    _antwort(["", "unsinn", "abc|PhotoViewerFacebook!.exe|", "777"], monkeypatch)
    assert viewer_control._running_pids(EXE) == []
