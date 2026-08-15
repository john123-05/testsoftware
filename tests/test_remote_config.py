"""Merkmale aus dem Dashboard schalten, ohne an den Automaten zu fahren.

Bis hierher liess sich ein Merkmal nur an der `.env` am Automaten umstellen.
Fuer Imst hiesse das: nach dem Rollout noch einmal hinfahren, um
Neustart-Knoepfe, Testfoto oder die Muenzauswertung einzuschalten.

Die wichtigste Regel steht in `test_fehlender_eintrag_aendert_nichts`: ein
Merkmal, das im Dashboard nicht gesetzt ist, wird NICHT geschrieben - es bleibt
stehen, was am Automaten steht. Die Tabelle darueber verhaelt sich umgekehrt
(leerer Serverwert -> harter Vorgabewert), und genau darueber wuerde eine Anlage
mit eigenen Pfaden auf die Standardpfade zurueckgesetzt.
"""
from liftpic_sync.remote_config import config_to_env


def basis(**extra) -> dict:
    werte = {
        "park_slug": "imster-bergbahnen",
        "park_id": "park-1",
        "legacy_customer_code": "2734",
        "machine_id": "pcneu",
        "camera_code": "cam1",
        "mode": "sold_only",
        "raw_dir": r"C:\liftpic\fotos",
        "processed_dir": r"C:\liftpic\fotos\out",
    }
    werte.update(extra)
    return werte


def test_fehlender_eintrag_aendert_nichts():
    """Der Kern: nicht gesetzt heisst nicht angefasst, nicht abgeschaltet."""
    env = config_to_env(basis(), "token")

    for schluessel in (
        "VIEWER_RESTART_ENABLED", "CAMERA_EXE", "TEST_PHOTO_EXE",
        "COIN_STATS_FILE", "CARD_LOG_GLOB", "ASSET_SYNC_ENABLED",
    ):
        assert schluessel not in env, (
            f"{schluessel} darf nicht geschrieben werden, wenn das Dashboard "
            "nichts dazu sagt - sonst schaltet ein Abruf ein Merkmal ab"
        )


def test_leeres_settings_feld_aendert_nichts():
    assert "CAMERA_EXE" not in config_to_env(basis(settings={}), "token")
    assert "CAMERA_EXE" not in config_to_env(basis(settings=None), "token")


def test_merkmal_einschalten():
    env = config_to_env(basis(settings={
        "viewer_restart_enabled": True,
        "camera_exe": r"C:\liftpic\3GerTis\3gerTis_v70.exe",
        "test_photo_exe": r"C:\liftpic\kosel\AidaTest.exe",
    }), "token")

    assert env["VIEWER_RESTART_ENABLED"] == "true"
    assert env["CAMERA_EXE"] == r"C:\liftpic\3GerTis\3gerTis_v70.exe"
    assert env["TEST_PHOTO_EXE"] == r"C:\liftpic\kosel\AidaTest.exe"


def test_merkmal_ausschalten_geht_auch():
    """Ausdruecklich `false` muss ankommen - sonst liesse sich ein Merkmal
    aus der Ferne einschalten, aber nie wieder abschalten."""
    env = config_to_env(basis(settings={"viewer_restart_enabled": False}), "token")

    assert env["VIEWER_RESTART_ENABLED"] == "false"


def test_leerer_pfad_schaltet_das_merkmal_ab():
    """Ein leerer Pfad ist die vorgesehene Art, ein Merkmal abzuschalten -
    der Agent behandelt einen leeren Wert als 'nicht eingerichtet'."""
    env = config_to_env(basis(settings={"test_photo_exe": ""}), "token")

    assert env["TEST_PHOTO_EXE"] == ""


def test_settings_ueberschreibt_die_pfade_der_haupttabelle_nicht():
    """Die beiden Tabellen duerfen sich nicht in die Quere kommen."""
    env = config_to_env(basis(
        raw_dir=r"D:\eigene\fotos",
        settings={"camera_exe": r"C:\kamera\prog.exe"},
    ), "token")

    assert env["RAW_DIR"] == r"D:\eigene\fotos"
    assert env["CAMERA_EXE"] == r"C:\kamera\prog.exe"


def test_protokollmuster_lassen_sich_fernstellen():
    """Damit ein Automat mit anderem Ablageort ohne Besuch sehend wird."""
    muster = r"D:\anlage\logs\*.txt;D:\anlage\kamera\*.log"
    env = config_to_env(basis(settings={"operational_log_globs": muster}), "token")

    assert env["OPERATIONAL_LOG_GLOBS"] == muster
