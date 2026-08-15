"""Was sich neu starten laesst - und vor allem, was NICHT.

Der wichtigste Punkt hier ist die Richtung der Vertrauensbeziehung: der Server
nennt einen Schluessel, der Automat entscheidet, welche Datei das ist. Ein Test,
der das festhaelt, ist mehr wert als jeder Kommentar - er faellt um, sobald
jemand den Pfad aus dem Auftrag uebernimmt.
"""
from pathlib import Path

from datetime import datetime, timedelta

from liftpic_sync.config import Settings
from liftpic_sync.viewer_control import (
    find_program, kamera_ist_verbunden, restart_program, restartable_programs,
    trigger_test_photo,
)


def _kameraordner(tmp_path: Path, zeilen: list[str]) -> Path:
    """Ein 3GerTis-Ordner mit Programm und Protokoll."""
    ordner = tmp_path / "3GerTis"
    ordner.mkdir(exist_ok=True)
    exe = ordner / "3gerTis_v70.exe"
    exe.write_bytes(b"MZ")
    (ordner / "3gerlog.txt").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return exe


def _stempel(minuten_her: float) -> str:
    return (datetime.now() - timedelta(minutes=minuten_her)).strftime("%d.%m.%Y\t%H:%M:%S")


def test_kamera_gilt_als_verbunden_nach_from_cam(tmp_path: Path):
    """"(from cam)" heisst: die Werte kamen aus der Kamera, sie war erreichbar.

    "(from ini)" erscheint auch ohne Kamera - nur aus der Konfigurationsdatei -
    und darf deshalb nicht als Verbindung zaehlen.
    """
    exe = _kameraordner(tmp_path, [
        f"{_stempel(20)}\tDevice lost",
        f"{_stempel(5)}\tGain (from ini) min=0, Gain max=4000000",
        f"{_stempel(5)}\tGain (from cam) min=0, Gain max=480",
    ])
    zustand, alter = kamera_ist_verbunden(make_settings(tmp_path, camera_exe=exe))

    assert zustand is True
    assert alter is not None and alter < 10


def test_juengste_aussage_gewinnt(tmp_path: Path):
    """Ein alter Geraeteverlust zaehlt nicht mehr, wenn danach verbunden wurde -
    und umgekehrt."""
    exe = _kameraordner(tmp_path, [
        f"{_stempel(60)}\tGain (from cam) min=0, Gain max=480",
        f"{_stempel(30)}\tDevice lost",
    ])
    zustand, _ = kamera_ist_verbunden(make_settings(tmp_path, camera_exe=exe))
    assert zustand is False


def test_ohne_protokoll_wird_nichts_behauptet(tmp_path: Path):
    """Kein Anhaltspunkt heisst "unbekannt", nicht "nicht verbunden"."""
    ordner = tmp_path / "leer"
    ordner.mkdir()
    exe = ordner / "3gerTis_v70.exe"
    exe.write_bytes(b"MZ")

    zustand, alter = kamera_ist_verbunden(make_settings(tmp_path, camera_exe=exe))

    assert zustand is None
    assert alter is None


def test_testfoto_wartet_nicht_auf_eine_fehlende_kamera(tmp_path: Path):
    """Ist die Kamera nachweislich weg, wird gar nicht erst ausgeloest.

    Am 15.08.2026 lief ein Testfoto 76 Sekunden nach dem Neustart der
    Kamera-Software ins Leere; die Kamera meldete sich erst 6,5 Minuten nach
    dem Start zurueck. Die Meldung nannte nur "Kamera hat nicht reagiert" -
    ohne den Grund und ohne den Hinweis, dass Warten genuegt.
    """
    ausloeser = tmp_path / "AidaTest.exe"
    ausloeser.write_bytes(b"MZ")

    # Gerade neu gestartet, Kamera noch nicht da: bitte warten.
    exe = _kameraordner(tmp_path, [f"{_stempel(2)}\tDevice lost"])
    frisch = trigger_test_photo(make_settings(
        tmp_path, camera_exe=exe, test_photo_exe=ausloeser,
    ))
    assert frisch.performed is False
    assert "neu gestartet" in frisch.reason
    assert "8 Minuten" in frisch.reason

    # Laenger weg: dann ist Warten keine Antwort mehr.
    exe = _kameraordner(tmp_path, [f"{_stempel(90)}\tDevice lost"])
    lange = trigger_test_photo(make_settings(
        tmp_path, camera_exe=exe, test_photo_exe=ausloeser,
    ))
    assert lange.performed is False
    assert "neu starten" in lange.reason


def make_settings(tmp_path: Path, **extra) -> Settings:
    raw = tmp_path / "fotos"
    out = raw / "out"
    raw.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    werte = dict(
        app_name="test",
        shadow_mode=True,
        park_slug="test-park",
        park_id="park-id",
        customer_code="1234",
        machine_id="machine",
        device_token="token",
        supabase_functions_url="http://example.test/functions/v1",
        supabase_url="http://example.test",
        supabase_anon_key="anon",
        raw_dir=raw,
        processed_dir=out,
        webout_dir=None,
        qrcode_dir=None,
        upload_source="qrcode",
        stage_in_shadow=False,
        statistic_file=None,
        print_count_file=None,
        app_dir=tmp_path,
        state_db=tmp_path / "state.db",
        log_dir=tmp_path / "logs",
        poll_seconds=0.1,
        file_stable_seconds=0,
        speed_match_seconds=12,
        speed_timeout_seconds=30,
        upload_retry_seconds=1,
        heartbeat_seconds=60,
        archive_raw=False,
        camera_code="cam1",
    )
    werte.update(extra)
    return Settings(**werte)


def _exe(tmp_path: Path, name: str) -> Path:
    pfad = tmp_path / name
    pfad.write_text("nicht wirklich ein Programm", encoding="utf-8")
    return pfad


def test_nothing_is_restartable_unless_configured(tmp_path: Path):
    """Ein unveraenderter PC verhaelt sich wie vorher: keine Knoepfe."""
    settings = make_settings(tmp_path)
    assert restartable_programs(settings) == []
    assert find_program(settings, "viewer") is None
    assert find_program(settings, "camera") is None


def test_master_switch_disables_everything(tmp_path: Path):
    """Ohne VIEWER_RESTART_ENABLED bleibt alles aus, auch bei gesetzten Pfaden."""
    settings = make_settings(
        tmp_path,
        viewer_restart_enabled=False,
        viewer_exe=_exe(tmp_path, "viewer.exe"),
        camera_exe=_exe(tmp_path, "kamera.exe"),
    )
    assert restartable_programs(settings) == []


def test_only_configured_and_existing_programs_are_offered(tmp_path: Path):
    """Ein hinterlegter, aber fehlender Pfad ergibt keinen Knopf.

    Sonst stuende im Dashboard ein Angebot, das beim Klick scheitert.
    """
    settings = make_settings(
        tmp_path,
        viewer_restart_enabled=True,
        viewer_exe=_exe(tmp_path, "viewer.exe"),
        camera_exe=tmp_path / "gibtesnicht.exe",
    )
    keys = [p.key for p in restartable_programs(settings)]
    assert keys == ["viewer"]


def test_server_cannot_name_a_path_only_a_key(tmp_path: Path):
    """Der Kern des Sicherheitsmodells.

    Ein Auftrag, der einen Pfad statt eines bekannten Schluessels enthaelt, wird
    abgelehnt - der Automat startet ausschliesslich, was in SEINER Konfiguration
    steht.
    """
    fremd = _exe(tmp_path, "rechner.exe")
    settings = make_settings(
        tmp_path,
        viewer_restart_enabled=True,
        viewer_exe=_exe(tmp_path, "viewer.exe"),
    )

    for boesartig in (str(fremd), "C:\\Windows\\System32\\cmd.exe", "../viewer.exe",
                      "uploader", "spooler", "cmd", "powershell"):
        assert find_program(settings, boesartig) is None, boesartig
        ergebnis = restart_program(settings, boesartig)
        assert ergebnis.performed is False


def test_missing_target_still_means_the_viewer(tmp_path: Path):
    """Ein Auftrag ohne Ziel meinte immer das Verkaufsprogramm.

    Solche Auftraege koennen noch gespeichert sein, aus der Zeit vor den
    Zielen. Sie duerfen nicht ins Leere laufen - aber auch nichts anderes
    treffen als frueher.
    """
    viewer = _exe(tmp_path, "viewer.exe")
    settings = make_settings(
        tmp_path,
        viewer_restart_enabled=True,
        viewer_exe=viewer,
        camera_exe=_exe(tmp_path, "kamera.exe"),
    )
    assert find_program(settings, "").exe == viewer
    assert find_program(settings, "viewer").exe == viewer


def test_known_key_resolves_to_the_configured_file(tmp_path: Path):
    viewer = _exe(tmp_path, "viewer.exe")
    kamera = _exe(tmp_path, "kamera.exe")
    settings = make_settings(
        tmp_path,
        viewer_restart_enabled=True,
        viewer_exe=viewer,
        camera_exe=kamera,
        lightbarrier_exe=_exe(tmp_path, "schranke.exe"),
    )

    assert find_program(settings, "camera").exe == kamera
    assert find_program(settings, "viewer").exe == viewer
    # Gross-/Kleinschreibung und Leerzeichen duerfen keine Rolle spielen.
    assert find_program(settings, "  CAMERA ").exe == kamera


def test_every_offered_program_explains_its_consequence(tmp_path: Path):
    """Kein Knopf ohne Ansage, was er fuer den Gast bedeutet."""
    settings = make_settings(
        tmp_path,
        viewer_restart_enabled=True,
        viewer_exe=_exe(tmp_path, "viewer.exe"),
        camera_exe=_exe(tmp_path, "kamera.exe"),
        lightbarrier_exe=_exe(tmp_path, "schranke.exe"),
    )
    programme = restartable_programs(settings)
    assert len(programme) == 3
    for p in programme:
        assert p.name and p.tech and p.folge
        # Klarname vorn, Technik dahinter - nie vermischt.
        assert p.tech not in p.name


def test_restart_orders_are_polled_far_more_often_than_assets(tmp_path: Path):
    """Ein Auftrag darf nicht am Bilder-Abruf haengen.

    Der Neustart-Auftrag reist mit dem Asset-Abruf mit. Der lief mit 300
    Sekunden - "jetzt neu starten" konnte also fuenf Minuten liegen bleiben,
    waehrend die Seite Fortschritt behauptete. Sobald Neustarts moeglich sind,
    zaehlt die Wartezeit des Betreibers, nicht die Aenderungsrate von Bildern.
    """
    from liftpic_sync.service import LiftpicService

    settings = make_settings(
        tmp_path,
        asset_sync_enabled=True,
        asset_sync_seconds=300,
        restart_poll_seconds=20,
        viewer_restart_enabled=True,
        viewer_exe=_exe(tmp_path, "viewer.exe"),
    )
    dienst = LiftpicService(settings)
    assert dienst._asset_poll_seconds() == 20

    # Ohne Neustart-Freigabe bleibt es beim ruhigen Takt: dann wartet niemand
    # vor dem Bildschirm auf eine Reaktion.
    ohne = make_settings(
        tmp_path,
        asset_sync_enabled=True,
        asset_sync_seconds=300,
        restart_poll_seconds=20,
        viewer_restart_enabled=False,
    )
    assert LiftpicService(ohne)._asset_poll_seconds() == 300


def test_ausgabe_vertraegt_fehlende_standardausgabe(monkeypatch):
    """Am echten Automaten aufgetreten.

    Der Agent laeuft ohne Konsole. Unter dieser Bedingung lieferte
    `tasklist.exe` `stdout = None`, und `str(pid) in None` warf einen
    TypeError - mitten im Neustart, nachdem das Programm bereits beendet war.
    """
    import subprocess as sp

    from liftpic_sync import viewer_control as vc

    class Leer:
        returncode = 0
        stdout = None
        stderr = None

    monkeypatch.setattr(sp, "run", lambda *a, **k: Leer())

    # Kein Absturz, sondern eine leere Antwort ...
    assert vc._ausgabe(["tasklist.exe"]) == ""
    # ... und daraus die sichere Annahme "laeuft nicht mehr".
    assert vc._pid_alive(4711) is False


def test_start_erfolgt_auch_wenn_das_anhalten_scheitert(tmp_path: Path, monkeypatch):
    """Der eigentliche Schaden war nicht der Fehler, sondern seine Folge.

    Das Verkaufsprogramm war beendet, dann flog beim Nachsehen ein Fehler - und
    der gemeinsame try-Block uebersprang den Start. Der Automat stand ohne
    Verkaufsprogramm da. Das darf nicht mehr passieren koennen.
    """
    from liftpic_sync import viewer_control as vc

    settings = make_settings(
        tmp_path,
        viewer_restart_enabled=True,
        viewer_exe=_exe(tmp_path, "viewer.exe"),
    )

    gestartet: list[str] = []

    def anhalten_kaputt(_exe):
        raise RuntimeError("Prozessliste nicht lesbar")

    class UnechterProzess:
        def __init__(self, befehl, **_kwargs):
            gestartet.append(befehl[0])

    monkeypatch.setattr(vc, "_running_pids", anhalten_kaputt)
    monkeypatch.setattr(vc.subprocess, "Popen", UnechterProzess)
    monkeypatch.setattr(vc.time, "sleep", lambda _s: None)

    ergebnis = vc.restart_program(settings, "viewer")

    # Gestartet wurde trotzdem - das ist der Punkt.
    assert len(gestartet) == 1
    assert gestartet[0].endswith("viewer.exe")
    # Und die Kontrolle scheiterte ebenfalls, das wird ehrlich gesagt.
    assert ergebnis.performed is True
    assert "Kontrolle" in ergebnis.reason


def test_testfoto_glaubt_dem_exitcode_nicht(tmp_path: Path, monkeypatch):
    """Der wichtigste Punkt beim Testfoto.

    Am echten Automaten lieferte `3GerImage.exe` Exitcode 0, obwohl die Kamera
    seit Tagen weg war - kein Bild, nicht einmal ein Protokolleintrag. Wer dem
    Rueckgabewert glaubt, meldet Erfolg fuer ein Foto, das es nicht gibt.
    """
    from liftpic_sync import viewer_control as vc

    settings = make_settings(
        tmp_path,
        test_photo_exe=_exe(tmp_path, "3gerimage.exe"),
    )

    class TutNichts:
        def __init__(self, *_a, **_k):
            pass

    monkeypatch.setattr(vc.subprocess, "Popen", TutNichts)
    monkeypatch.setattr(vc.time, "sleep", lambda _s: None)
    # Zeit vorspulen, damit die Warteschleife endet, ohne wirklich zu warten.
    uhr = iter([0.0] + [100.0] * 50)
    monkeypatch.setattr(vc.time, "time", lambda: next(uhr, 100.0))

    ergebnis = vc.trigger_test_photo(settings)

    assert ergebnis.performed is False
    assert "Kein Bild entstanden" in ergebnis.reason


def test_testfoto_zaehlt_erst_mit_neuer_datei(tmp_path: Path, monkeypatch):
    """Erfolg heisst: es liegt wirklich ein neues Bild da."""
    from liftpic_sync import viewer_control as vc

    settings = make_settings(
        tmp_path,
        test_photo_exe=_exe(tmp_path, "3gerimage.exe"),
    )

    class LegtBildAb:
        def __init__(self, *_a, **_k):
            (settings.raw_dir / "00001.jpg").write_bytes(b"bild")

    monkeypatch.setattr(vc.subprocess, "Popen", LegtBildAb)
    monkeypatch.setattr(vc.time, "sleep", lambda _s: None)

    ergebnis = vc.trigger_test_photo(settings)

    # Der Erfolg haengt an der Datei, nicht am Rueckgabewert des Programms.
    assert ergebnis.performed is True
    assert "aufgenommen" in ergebnis.reason


def test_testfoto_ohne_einrichtung_wird_abgelehnt(tmp_path: Path):
    from liftpic_sync.viewer_control import trigger_test_photo

    ergebnis = trigger_test_photo(make_settings(tmp_path))

    assert ergebnis.performed is False
    assert "nicht eingerichtet" in ergebnis.reason


def test_uploader_is_never_restartable(tmp_path: Path):
    """Der Agent darf sich nicht selbst abschiessen.

    Nichts auf dem Automaten wuerde ihn wieder starten - weder Autostart noch
    Dienst. Danach waere der Automat unbeobachtet und nicht mehr erreichbar.
    """
    settings = make_settings(
        tmp_path,
        viewer_restart_enabled=True,
        viewer_exe=_exe(tmp_path, "viewer.exe"),
        camera_exe=_exe(tmp_path, "kamera.exe"),
        lightbarrier_exe=_exe(tmp_path, "schranke.exe"),
    )
    keys = {p.key for p in restartable_programs(settings)}
    assert "uploader" not in keys
    assert "liftpic-sync" not in keys
    assert find_program(settings, "uploader") is None
