import os
import time
from pathlib import Path
from types import SimpleNamespace

from liftpic_sync import service as service_mod
from liftpic_sync.service import LiftpicService


def _dienst(tmp_path: Path, code: str = "3344", minuten: float = 60):
    raw = tmp_path / "fotos"
    out = raw / "out"
    out.mkdir(parents=True)
    settings = SimpleNamespace(
        sample_upload_minutes=minuten, customer_code=code,
        processed_dir=out, raw_dir=raw,
    )
    return SimpleNamespace(
        settings=settings, client=object(),
        _letzte_stichprobe=0.0, _letztes_stichprobenbild=None,
    ), raw, out


def _hochgeladen(monkeypatch):
    liste = []
    monkeypatch.setattr(
        service_mod, "lade_testfoto_hoch",
        lambda settings, client, bild: liste.append(bild.name) or f"x/{bild.name}",
    )
    return liste


def test_laedt_neuestes_bild_einmal_pro_zeitraum(tmp_path, monkeypatch):
    dienst, raw, out = _dienst(tmp_path)
    (raw / "00001.jpg").write_bytes(b"a")
    alt = time.time() - 30
    os.utime(raw / "00001.jpg", (alt, alt))
    (out / "Img75883.jpg").write_bytes(b"b")
    liste = _hochgeladen(monkeypatch)

    LiftpicService._stichprobe_if_due(dienst)
    LiftpicService._stichprobe_if_due(dienst)  # gleich danach: noch nicht wieder
    assert liste == ["Img75883.jpg"]


def test_nichts_ohne_kundennummer(tmp_path, monkeypatch):
    dienst, raw, _ = _dienst(tmp_path, code="0000")
    (raw / "00001.jpg").write_bytes(b"a")
    liste = _hochgeladen(monkeypatch)
    LiftpicService._stichprobe_if_due(dienst)
    assert liste == []


def test_nichts_wenn_anlage_steht(tmp_path, monkeypatch):
    dienst, raw, _ = _dienst(tmp_path)
    (raw / "00001.jpg").write_bytes(b"a")
    alt = time.time() - 3 * 3600
    os.utime(raw / "00001.jpg", (alt, alt))
    liste = _hochgeladen(monkeypatch)
    LiftpicService._stichprobe_if_due(dienst)
    assert liste == []


def test_aus_wenn_null(tmp_path, monkeypatch):
    dienst, raw, _ = _dienst(tmp_path, minuten=0)
    (raw / "00001.jpg").write_bytes(b"a")
    liste = _hochgeladen(monkeypatch)
    LiftpicService._stichprobe_if_due(dienst)
    assert liste == []


def test_fernschaltbar():
    from liftpic_sync.remote_config import config_to_env
    env = config_to_env({"mode": "count_only", "settings": {"sample_upload_minutes": 60}}, "t")
    assert env["SAMPLE_UPLOAD_MINUTES"] == "60"


def test_viewer_kundennummer_aus_settings(tmp_path):
    from liftpic_sync.service import _viewer_customer_number
    xml = tmp_path / "Settings.xml"
    xml.write_text("<Settings><CustomerNumber>3344</CustomerNumber></Settings>", encoding="utf-8")
    assert _viewer_customer_number(SimpleNamespace(viewer_settings_xml=xml)) == "3344"
    assert _viewer_customer_number(SimpleNamespace(viewer_settings_xml=tmp_path / "fehlt.xml")) is None
