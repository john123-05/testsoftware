"""EOS-Utility-Erkennung (Kalahari) und die lokale Liftpictures Station."""
from dataclasses import replace
import json
from pathlib import Path

from liftpic_sync.camera_settings import kamera_status
from liftpic_sync.remote_config import config_to_env
from liftpic_sync.service import LiftpicService
from liftpic_sync.station import schreibe_station
from liftpic_sync.station_page import PAGE
from liftpic_sync.system_probe import DEFAULT_PROCESSES, PROGRAM_TECH
from liftpic_sync.viewer_control import kamera_tech

from test_service import FakeStatusClient, make_settings

EOS = Path(r"C:\Program Files (x86)\Canon\EOS Utility\EU3\EOS Utility 3.exe")


def _service(tmp_path: Path, **extra) -> LiftpicService:
    settings = replace(make_settings(tmp_path), **extra)
    return LiftpicService(settings)


# ---------------------------------------------------------------- Erkennung

def test_eos_utility_zaehlt_als_kamera_software():
    kamera = [w for w in DEFAULT_PROCESSES if w[1] == "Kamera-Software"][0]
    namen = [n.lower() for n in kamera[0].split("|")]
    assert "eos utility 3" in namen
    # Der Schluessel bleibt beim ersten Namen, sonst reisst die Historie ab.
    assert namen[0] == "3gertis_v70"
    assert PROGRAM_TECH["eos utility 3"] == "Canon EOS Utility"


def test_kamera_tech_aus_dem_programmpfad():
    assert kamera_tech(EOS) == "Canon EOS Utility"
    assert kamera_tech(Path(r"C:\cam\camera26.exe")) == "TIScapture"
    assert kamera_tech(Path(r"C:\cam\3gerTis_v70.exe")) == "3GerTis"


def test_eos_utility_hat_keine_kameraseite(tmp_path: Path):
    settings = replace(make_settings(tmp_path), camera_exe=EOS)
    assert kamera_status(settings) is None


# --------------------------------------------------------------- Fernschalter

def test_station_und_ausblenden_sind_fernschaltbar():
    env = config_to_env({
        "park_slug": "kalahari-virginia", "park_id": "p", "machine_id": "m",
        "settings": {
            "station_enabled": False,
            "probe_skip_programs": ["Verkaufsprogramm", "Lichtschranke"],
        },
    }, "token")
    assert env["STATION_ENABLED"] == "false"
    assert env["PROBE_SKIP_PROGRAMS"] == "Verkaufsprogramm,Lichtschranke"


def test_ohne_eintrag_bleibt_alles_unangetastet():
    env = config_to_env({"park_slug": "x", "park_id": "p", "machine_id": "m"}, "token")
    assert "STATION_ENABLED" not in env
    assert "PROBE_SKIP_PROGRAMS" not in env


def test_agent_startet_die_kamera_nie_selbst():
    # Ausdruecklich gewollt (John, 04.11.2026): wer die Kamera-Software
    # ausschaltet, soll sie nicht von selbst wiederkommen sehen.
    import liftpic_sync.service as svc
    assert not hasattr(svc.LiftpicService, "_camera_keepalive_if_due")
    env = config_to_env({"park_slug": "x", "park_id": "p", "machine_id": "m",
                         "settings": {"camera_keepalive": True}}, "token")
    assert "CAMERA_KEEPALIVE" not in env


# ------------------------------------------------------------------ Station

def test_station_schreibt_seite_und_stand(tmp_path: Path):
    ordner = tmp_path / "station"
    schreibe_station(ordner, {"park_slug": "kalahari-virginia", "probes": [], "note": "a</script>b"})
    assert (ordner / "index.html").read_text(encoding="utf-8") == PAGE
    js = (ordner / "status.js").read_text(encoding="utf-8")
    assert js.startswith("window.__station&&window.__station(")
    assert "</script>" not in js
    daten = json.loads(js[len("window.__station&&window.__station("):-3].replace("<\\/", "</"))
    assert daten["park_slug"] == "kalahari-virginia"
    assert not list(ordner.glob("*.tmp"))


def test_herzschlag_schreibt_station_auch_offline(tmp_path: Path):
    station = tmp_path / "station"
    svc = _service(tmp_path, station_dir=station, station_enabled=True, probe_enabled=False)

    class Kaputt:
        def status(self, payload):
            raise RuntimeError("no internet")

    svc.client = Kaputt()
    svc._heartbeat_if_due({"queued": 3})
    js = (station / "status.js").read_text(encoding="utf-8")
    assert '"online":false' in js
    assert '"queue_count":3' in js

    svc.client = FakeStatusClient()
    svc._last_heartbeat = 0
    svc._heartbeat_if_due({"queued": 0})
    assert '"online":true' in (station / "status.js").read_text(encoding="utf-8")


def test_seite_braucht_kein_internet():
    # Keine fremden Skripte, Schriften oder Bilder: die Seite muss offline laufen.
    assert "http://" not in PAGE and "https://" not in PAGE
