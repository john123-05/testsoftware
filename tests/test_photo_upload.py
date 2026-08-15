"""Das Testfoto darf niemals im falschen Park landen.

Am 14.08.2026 sind vier Fotos dieses Testrechners in Imsts Umsatz aufgetaucht,
weil der Server aus dem Dateinamen keine Kundennummer lesen konnte und auf die
Zuordnung Bucket -> Park zurueckfiel. Bucket `test` zeigt auf Imst.

Ein Testfoto heisst roh `00001.jpg` und haette exakt denselben Weg genommen.
Diese Tests halten die Bremse fest, die das verhindert.
"""
from datetime import datetime
from pathlib import Path

import pytest

from liftpic_sync.config import Settings
from liftpic_sync.test_photo_upload import (
    NichtZuordenbar, baue_metadaten, lade_testfoto_hoch,
    pruefe_name_ist_zuordenbar,
)


def make_settings(tmp_path: Path, **extra) -> Settings:
    raw = tmp_path / "fotos"
    out = raw / "out"
    raw.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    werte = dict(
        app_name="test", shadow_mode=False, park_slug="testrechner",
        park_id="park-id", customer_code="1234", machine_id="machine",
        device_token="token",
        supabase_functions_url="http://example.test/functions/v1",
        supabase_url="http://example.test", supabase_anon_key="anon",
        raw_dir=raw, processed_dir=out, webout_dir=None, qrcode_dir=None,
        upload_source="qrcode", stage_in_shadow=False, statistic_file=None,
        print_count_file=None, app_dir=tmp_path,
        state_db=tmp_path / "state.db", log_dir=tmp_path / "logs",
        poll_seconds=0.1, file_stable_seconds=0, speed_match_seconds=12,
        speed_timeout_seconds=30, upload_retry_seconds=1, heartbeat_seconds=60,
        archive_raw=False, camera_code="1234",
    )
    werte.update(extra)
    return Settings(**werte)


def _bild(tmp_path: Path, name: str = "00001.jpg") -> Path:
    pfad = tmp_path / "fotos" / name
    pfad.parent.mkdir(exist_ok=True)
    pfad.write_bytes(b"ein bild")
    return pfad


# ------------------------------------------------------------------- Bremse

def test_rohname_wird_abgelehnt():
    """`00001.jpg` ist genau der Name, der nach Imst gefuehrt haette."""
    with pytest.raises(NichtZuordenbar) as fehler:
        pruefe_name_ist_zuordenbar("00001.jpg", "1234")
    assert "fremden Park" in str(fehler.value)


@pytest.mark.parametrize("name", [
    "foto.jpg", "1234.jpg", "123456789012345.jpg",     # zu kurz
    "12345678901234567.jpg",                            # zu lang
    "abcdefghijklmnop.jpg", "1234567890123456.png",
])
def test_nur_echte_codenamen_sind_erlaubt(name):
    with pytest.raises(NichtZuordenbar):
        pruefe_name_ist_zuordenbar(name, "1234")


def test_fremde_kundennummer_wird_abgelehnt(tmp_path: Path):
    """Ein gueltiger Code, aber vom falschen Automaten - auch das nicht."""
    settings = make_settings(tmp_path, customer_code="1234")
    name, _ = baue_metadaten(settings, _bild(tmp_path))
    # Derselbe Name, aber ein Automat mit anderer Kundennummer erwartet ihn.
    with pytest.raises(NichtZuordenbar) as fehler:
        pruefe_name_ist_zuordenbar(name, "7623")
    assert "Kundennummer" in str(fehler.value)


# ------------------------------------------------------------------ Aufbau

def test_metadaten_tragen_einen_zuordenbaren_namen(tmp_path: Path):
    settings = make_settings(tmp_path, customer_code="1234")

    name, metadaten = baue_metadaten(settings, _bild(tmp_path))

    assert len(name) == 20 and name.endswith(".jpg")   # 16 Ziffern + .jpg
    assert metadaten["is_test"] is True
    assert metadaten["park_slug"] == "testrechner"
    # Der Name muss die eigene Kundennummer tragen, sonst greift die Bremse.
    pruefe_name_ist_zuordenbar(name, "1234")


def test_zwei_testfotos_bekommen_verschiedene_schluessel(tmp_path: Path):
    """Sonst ueberschreibt das zweite Testfoto das erste."""
    settings = make_settings(tmp_path)
    _, eins = baue_metadaten(settings, _bild(tmp_path, "00001.jpg"))
    _, zwei = baue_metadaten(settings, _bild(tmp_path, "00002.jpg"))
    assert eins["event_key"] != zwei["event_key"]


# ------------------------------------------------------------------ Upload

class UnechterClient:
    def __init__(self, ablagepfad: str):
        self.ablagepfad = ablagepfad
        self.hochgeladen: list[str] = []

    def begin(self, metadaten, groesse):
        self.letzte_metadaten = metadaten
        return {"upload": {
            "bucket": "test", "storage_path": self.ablagepfad,
            "token": "t", "signed_url": "https://example.test/u",
        }}

    def upload_signed(self, **kwargs):
        self.hochgeladen.append(kwargs["storage_path"])

    def commit(self, *args, **kwargs):
        pass


def test_upload_setzt_das_testkennzeichen(tmp_path: Path):
    settings = make_settings(tmp_path)
    client = UnechterClient("processed/testrechner/testfoto/2026-08-14/1234.jpg")

    pfad = lade_testfoto_hoch(settings, client, _bild(tmp_path))

    assert "/testfoto/" in pfad
    assert client.letzte_metadaten["is_test"] is True
    assert client.hochgeladen == [pfad]


def test_juengstes_bild_findet_die_neueste_datei(tmp_path: Path):
    """Diese Funktion wurde nur zur Laufzeit ausgefuehrt - und flog dort auf.

    Ein fehlender Import (`Path`) faellt beim blossen Importieren des Moduls
    nicht auf, sondern erst beim Aufruf. Genau das ist passiert: der Agent lief
    an, und erst beim Testfoto kam `NameError: name 'Path' is not defined`.
    Deshalb wird die Funktion hier wirklich aufgerufen.
    """
    import os
    import time as zeitmodul

    from liftpic_sync.service import _juengstes_bild

    ordner = tmp_path / "fotos"
    ordner.mkdir(exist_ok=True)
    assert _juengstes_bild(ordner) is None          # leerer Ordner
    assert _juengstes_bild(None) is None            # gar kein Ordner
    assert _juengstes_bild(tmp_path / "gibtesnicht") is None

    alt = ordner / "00001.jpg"
    alt.write_bytes(b"alt")
    neu = ordner / "00002.jpg"
    neu.write_bytes(b"neu")
    # Aenderungszeiten eindeutig auseinanderziehen, damit der Vergleich nicht
    # an der Aufloesung der Dateizeit haengt.
    jetzt = zeitmodul.time()
    os.utime(alt, (jetzt - 60, jetzt - 60))
    os.utime(neu, (jetzt, jetzt))

    assert _juengstes_bild(ordner) == neu

    # Was kein Bild ist, zaehlt nicht mit.
    (ordner / "notiz.txt").write_bytes(b"kein bild")
    assert _juengstes_bild(ordner) == neu


def test_upload_bricht_ab_wenn_der_server_das_kennzeichen_ignoriert(tmp_path: Path):
    """Ohne /testfoto/ im Pfad waere es ein ganz normaler Verkauf.

    Das passiert, solange `liftpic-ingest-begin` die aeltere Fassung ohne
    `is_test` faehrt. Dann lieber gar nichts hochladen.
    """
    settings = make_settings(tmp_path)
    client = UnechterClient("processed/testrechner/2026-08-14/1234.jpg")

    with pytest.raises(RuntimeError) as fehler:
        lade_testfoto_hoch(settings, client, _bild(tmp_path))

    assert "nicht als Testfoto" in str(fehler.value)
    assert client.hochgeladen == []      # nichts ist rausgegangen
