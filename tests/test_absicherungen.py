"""Die Absicherungen für den Rollout auf laufende Anlagen.

Jede dieser Prüfungen steht für einen Schaden, der schon eingetreten ist oder
unmittelbar drohte. Sie sind der Grund, warum ein Update an einer Anlage wie
Imst gefahrlos ist - fällt eine davon um, ist es das nicht mehr.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from liftpic_sync.config import Settings


def make_settings(tmp_path: Path, **extra) -> Settings:
    raw = tmp_path / "fotos"
    out = raw / "out"
    raw.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    werte = dict(
        app_name="test", shadow_mode=True, park_slug="park", park_id="park-id",
        customer_code="2734", machine_id="machine", device_token="token",
        supabase_functions_url="http://example.test/functions/v1",
        supabase_url="http://example.test", supabase_anon_key="anon",
        raw_dir=raw, processed_dir=out, webout_dir=None, qrcode_dir=None,
        upload_source="qrcode", stage_in_shadow=False, statistic_file=None,
        print_count_file=None, app_dir=tmp_path,
        state_db=tmp_path / "state.db", log_dir=tmp_path / "logs",
        poll_seconds=0.1, file_stable_seconds=0, speed_match_seconds=12,
        speed_timeout_seconds=30, upload_retry_seconds=1, heartbeat_seconds=60,
        archive_raw=False, camera_code="cam1",
    )
    werte.update(extra)
    return Settings(**werte)


def _settings_xml(tmp_path: Path, kundennummer: str) -> Path:
    pfad = tmp_path / "Settings.xml"
    pfad.write_text(
        f"<Settings>\n"
        f"  <CustomerNumber>{kundennummer}</CustomerNumber>\n"
        f"  <CodePositionsInFilename>2,3,4,5</CodePositionsInFilename>\n"
        f"</Settings>\n",
        encoding="utf-8",
    )
    return pfad


# --------------------------------------------------- 0.1 Abholcode bleibt

def test_abholcode_wird_ohne_freigabe_nicht_uebernommen(tmp_path: Path):
    """Der Vorfall vom 15.08.2026 in einem Test.

    Der Automat war auf 2734 konfiguriert, das Verkaufsprogramm sagte 1234.
    Frueher uebernahm der Agent die 1234 - und weil der Server den Park aus
    dieser Nummer ableitet, landete der naechste Upload beim falschen Kunden.
    """
    settings = make_settings(
        tmp_path,
        customer_code="2734",
        viewer_settings_xml=_settings_xml(tmp_path, "1234"),
        # Vorgabe, hier nur zur Verdeutlichung ausgeschrieben:
        viewer_recipe_enabled=False,
    )

    ergebnis = settings.with_viewer_recipe()

    assert ergebnis.customer_code == "2734", (
        "Ohne ausdrueckliche Freigabe darf die Kundennummer einer laufenden "
        "Anlage sich niemals aendern"
    )


def test_abholcode_wird_mit_freigabe_uebernommen(tmp_path: Path):
    """Wer es einschaltet, bekommt das alte Verhalten - bewusst."""
    settings = make_settings(
        tmp_path,
        customer_code="2734",
        viewer_settings_xml=_settings_xml(tmp_path, "1234"),
        viewer_recipe_enabled=True,
    )

    assert settings.with_viewer_recipe().customer_code == "1234"


def test_vorgabe_ist_aus(tmp_path: Path):
    """Eine .env ohne den Schalter darf nichts uebernehmen.

    Genau das ist der Fall bei jeder bestehenden Anlage, die aktualisiert wird.
    """
    env = tmp_path / ".env"
    env.write_text(
        "APP_NAME=test\nPARK_SLUG=park\nPARK_ID=id\nCUSTOMER_CODE=2734\n"
        "MACHINE_ID=m\nDEVICE_TOKEN=t\n"
        "SUPABASE_FUNCTIONS_URL=http://x/functions/v1\nSUPABASE_URL=http://x\n"
        "SUPABASE_ANON_KEY=a\n"
        f"RAW_DIR={tmp_path}\\fotos\nPROCESSED_DIR={tmp_path}\\fotos\\out\n"
        f"APP_DIR={tmp_path}\nSTATE_DB={tmp_path}\\s.db\nLOG_DIR={tmp_path}\\logs\n",
        encoding="utf-8",
    )
    settings = Settings.from_env_file(env)
    assert settings.viewer_recipe_enabled is False


# ------------------------------------------- 0.2 Kein Neustart ohne Schirm

def test_ohne_bildschirm_gibt_es_keine_neustart_ziele(tmp_path: Path, monkeypatch):
    """Ein Neustart aus Sitzung 0 wuerde den Automaten faktisch abschalten.

    Das sichtbare Verkaufsprogramm ginge aus, das neue liefe unsichtbar in
    Sitzung 0 weiter. Am Testrechner faellt das nie auf, weil der Agent dort
    als angemeldeter Benutzer laeuft.
    """
    from liftpic_sync import viewer_control as vc

    exe = tmp_path / "viewer.exe"
    exe.write_text("x", encoding="utf-8")
    settings = make_settings(tmp_path, viewer_restart_enabled=True, viewer_exe=exe,
                             test_photo_exe=exe)

    monkeypatch.setattr(vc, "laeuft_ohne_bildschirm", lambda: False)
    assert [p.key for p in vc.restartable_programs(settings)] == ["viewer"]

    monkeypatch.setattr(vc, "laeuft_ohne_bildschirm", lambda: True)
    assert vc.restartable_programs(settings) == []

    ergebnis = vc.trigger_test_photo(settings)
    assert ergebnis.performed is False
    assert "Bildschirmzugriff" in ergebnis.reason


def test_sitzungspruefung_sagt_im_zweifel_nichts(monkeypatch):
    """Kann die Sitzung nicht bestimmt werden, verschwindet nichts grundlos."""
    from liftpic_sync import viewer_control as vc

    class KaputtesCtypes:
        def __getattr__(self, _name):
            raise OSError("keine Windows-API")

    monkeypatch.setitem(__import__("sys").modules, "ctypes", KaputtesCtypes())
    assert vc.laeuft_ohne_bildschirm() is False


# ------------------------------------------------ 0.5 preflight ist lesend

def test_preflight_veraendert_nichts(tmp_path: Path):
    """Der Bericht muss auf einer produktiven Anlage gefahrlos laufen.

    Kein Ordner, keine Protokolldatei, keine Zustandsdatenbank darf dabei
    entstehen - sonst waere schon das Nachsehen ein Eingriff.
    """
    from liftpic_sync.preflight import bericht

    arbeit = tmp_path / "leer"
    arbeit.mkdir()
    settings = make_settings(
        tmp_path,
        app_dir=arbeit,
        state_db=arbeit / "state" / "s.db",
        log_dir=arbeit / "logs",
        viewer_settings_xml=_settings_xml(tmp_path, "1234"),
    )

    vorher = sorted(p.name for p in arbeit.iterdir())
    text = bericht(settings)
    nachher = sorted(p.name for p in arbeit.iterdir())

    assert vorher == nachher == [], "preflight hat etwas angelegt"
    # Und der Bericht muss das Wesentliche wirklich benennen.
    for abschnitt in ("ZUORDNUNG", "BILDSCHIRMZUGRIFF", "PROGRAMME",
                      "WAS SICH EINSCHALTEN WÜRDE"):
        assert abschnitt in text


def test_preflight_meldet_abweichende_kundennummer(tmp_path: Path):
    """Der wichtigste Satz im Bericht - deshalb festgehalten."""
    from liftpic_sync.preflight import bericht

    settings = make_settings(
        tmp_path,
        customer_code="2734",
        viewer_settings_xml=_settings_xml(tmp_path, "1234"),
    )
    text = bericht(settings)

    assert "ABWEICHUNG" in text
    assert "2734" in text and "1234" in text


# ------------------------------------------ 0.3 Alte Auftraege verfallen

def test_alter_auftrag_wird_verworfen():
    from liftpic_sync.service import (
        AUFTRAG_MAX_ALTER_MINUTEN, _auftragsalter_minuten,
    )

    frisch = {"requested_at": datetime.now(timezone.utc).isoformat()}
    assert _auftragsalter_minuten(frisch) < 1

    alt = {
        "requested_at": (
            datetime.now(timezone.utc) - timedelta(minutes=AUFTRAG_MAX_ALTER_MINUTEN + 5)
        ).isoformat()
    }
    assert _auftragsalter_minuten(alt) > AUFTRAG_MAX_ALTER_MINUTEN

    # Supabase schreibt 'Z' statt '+00:00' - das muss gelesen werden koennen.
    mit_z = {"requested_at": "2026-08-15T06:00:00Z"}
    assert _auftragsalter_minuten(mit_z) is not None

    # Ohne verwertbaren Zeitstempel wird nichts behauptet und nichts verworfen.
    assert _auftragsalter_minuten({}) is None
    assert _auftragsalter_minuten({"requested_at": "irgendwas"}) is None
