"""Liftpictures Kiosk: Daten fuer das neue Verkaufsprogramm."""
import json
import os
import time
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from liftpic_sync.kiosk import Kiosk, fotos_des_tages, host_einstellungen, letzte_verkaeufe, lies_konfig, verkaeufe
from liftpic_sync.remote_config import config_to_env
from liftpic_sync.service import LiftpicService

from test_service import make_settings

SETTINGS_XML = """<?xml version="1.0"?>
<Settings>
  <PhotoFolder>C:\\liftpic\\fotos\\</PhotoFolder>
  <PrinterName>DS-RX1</PrinterName>
  <PhotoWidth>155</PhotoWidth>
  <PhotoHeight>116</PhotoHeight>
  <QrCodeBeginningString>https://liftpictures-fotos.de/kalahari-virginia/claim?code=</QrCodeBeginningString>
  <QrCodeSize>16</QrCodeSize>
  <CreditCardExecutablePath>c:\\liftpic\\terminal\\easyzvt.exe</CreditCardExecutablePath>
  <CreditCardRegistryAmountParameter>Software\\GUB\\ZVT\\Betrag</CreditCardRegistryAmountParameter>
  <CreditCardRegistryResultParameter>Software\\GUB\\ZVT\\Ergebnis</CreditCardRegistryResultParameter>
  <EnablePrintDate>true</EnablePrintDate>
  <EnablePrintTime>false</EnablePrintTime>
</Settings>
"""


def _fotos(ordner: Path, namen: list[str], start: datetime) -> None:
    ordner.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(namen):
        datei = ordner / name
        datei.write_bytes(b"\xff\xd8\xff\xd9")
        t = start.timestamp() + 90 * i
        os.utime(datei, (t, t))


def _daten(ordner: Path) -> dict:
    text = (ordner / "data.js").read_text(encoding="utf-8")
    praefix = "window.__kiosk&&window.__kiosk("
    assert text.startswith(praefix)
    return json.loads(text[len(praefix):-3])


def test_fotos_des_tages_ohne_alte_und_halb_geschriebene(tmp_path: Path):
    jetzt = datetime(2026, 11, 5, 15, 0).timestamp()
    ordner = tmp_path / "fotos"
    _fotos(ordner, ["I00010.JPG"], datetime(2026, 11, 4, 9, 0))   # 30 h alt
    _fotos(ordner, ["I00011.JPG", "I00012.JPG"], datetime(2026, 11, 5, 14, 0))
    (ordner / "notiz.txt").write_text("x")
    frisch = ordner / "I00013.JPG"
    frisch.write_bytes(b"x")
    os.utime(frisch, (jetzt - 0.5, jetzt - 0.5))
    namen = [p.name for p, _ in fotos_des_tages(ordner, jetzt)]
    assert namen == ["I00012.JPG", "I00011.JPG"]


def test_schreibt_fotos_mit_code_link_und_host_json(tmp_path: Path):
    fotos = tmp_path / "fotos"
    _fotos(fotos, [f"I000{n}.JPG" for n in range(50, 58)], datetime(2026, 11, 4, 9, 40))
    xml = tmp_path / "samuel_neu" / "Settings.xml"
    xml.parent.mkdir()
    xml.write_text(SETTINGS_XML, encoding="latin-1")
    ziel = tmp_path / "kiosk-data"
    k = Kiosk(ziel)
    assert k.schreibe(raw_dir=fotos, viewer_xml=xml, customer_code="4761", positionen="3,4,5,6",
                      park_slug="kalahari-virginia", lizenziert=True, gueltig_bis="2026-12-31",
                      konfig='{"edition":"cash","products":{"print":{"price":700}},"boese":1}',
                      statistic_file=Path(r"C:\liftpic\samuel_neu\Statistic.txt"),
                      machine_id="kalahari-va-ropes-01",
                      jetzt=datetime(2026, 11, 4, 12, 0).timestamp())
    d = _daten(ziel)
    assert d["licensed"] is True and d["valid_until"] == "2026-12-31"
    assert [f["number"] for f in d["photos"]][:3] == ["0057", "0056", "0055"]
    erstes = d["photos"][0]
    assert erstes["file"] == "I00057.JPG"
    assert erstes["url"] == "https://liftpictures-fotos.de/kalahari-virginia/claim?code=" + erstes["code"]
    assert len(erstes["code"]) == 16 and erstes["ts"] > 0
    assert d["config"] == {"edition": "cash", "products": {"print": {"price": 700}}}
    assert d["base"]["links"]["download"] == "https://liftpictures-fotos.de/kalahari-virginia/claim?code={code}"
    host = json.loads((ziel / "host.json").read_text(encoding="utf-8"))
    assert host["photo_dir"] == str(fotos)
    assert host["card"]["amount_key"] == r"Software\GUB\ZVT\Betrag"
    assert host["card"]["result_key"] == r"Software\GUB\ZVT\Ergebnis"
    assert host["printer"]["name"] == "DS-RX1" and host["printer"]["photo_w_mm"] == 155
    assert host["cash"]["lib_dir"] == str(xml.parent)
    assert host["face"]["client"].endswith("FaceAiSharpClient.exe")
    assert (ziel / "sales").is_dir()
    # Unveraendert: nichts neu schreiben.
    assert not k.schreibe(raw_dir=fotos, viewer_xml=xml, customer_code="4761", positionen="3,4,5,6",
                          park_slug="kalahari-virginia", lizenziert=True, gueltig_bis="2026-12-31",
                          konfig='{"edition":"cash","products":{"print":{"price":700}},"boese":1}',
                          statistic_file=Path(r"C:\liftpic\samuel_neu\Statistic.txt"),
                          machine_id="kalahari-va-ropes-01",
                          jetzt=datetime(2026, 11, 4, 12, 0).timestamp())


def test_ohne_lizenz_keine_fotos(tmp_path: Path):
    fotos = tmp_path / "fotos"
    _fotos(fotos, ["I00057.JPG"], datetime(2026, 11, 4, 9, 40))
    ziel = tmp_path / "kiosk-data"
    Kiosk(ziel).schreibe(raw_dir=fotos, viewer_xml=None, customer_code="4761", positionen="3,4,5,6",
                         park_slug="p", lizenziert=False, grund="expired",
                         jetzt=datetime(2026, 11, 4, 12, 0).timestamp())
    d = _daten(ziel)
    assert d["licensed"] is False and d["reason"] == "expired" and d["photos"] == []


def test_konfig_nur_bekannte_bereiche():
    assert lies_konfig("kaputt") == {}
    assert lies_konfig("[1,2]") == {}
    assert lies_konfig('{"payments":["cash"],"x":1}') == {"payments": ["cash"]}
    assert lies_konfig({"theme": {"preset": "night"}}) == {"theme": {"preset": "night"}}
    assert lies_konfig("{" + '"a":1,' * 20000 + '"b":2}') == {}


def test_host_vorgaben_ohne_settings_xml(tmp_path: Path):
    h = host_einstellungen(raw_dir=tmp_path, viewer_xml=None, viewer=None, statistic_file=None,
                           print_count_file=None, sold_dir=None, coin_stats_file=None)
    assert h["card"]["exe"] == r"c:\liftpic\terminal\easyzvt.exe"
    assert h["card"]["timeout_seconds"] == 120
    assert h["printer"]["qr"] is True and h["statistic_file"] is None


def test_verkaeufe_fuer_herzschlag_und_freischaltung(tmp_path: Path):
    sales = tmp_path / "sales"
    sales.mkdir()
    jetzt = datetime(2026, 11, 5, 15, 0)
    zeilen = [
        {"id": "a1", "at": "2026-11-05T10:00:00+01:00", "method": "cash", "amount_cents": 900,
         "items": [{"code": "4456000000000001", "format": "combo"}]},
        {"id": "a2", "at": "2026-11-05T14:50:00+01:00", "method": "card", "amount_cents": 1200,
         "items": [{"code": "4456000000000002", "format": "digital"}, {"code": "4456000000000003", "format": "digital"}]},
    ]
    (sales / "2026-11-05.jsonl").write_text("\n".join(json.dumps(z) for z in zeilen) + "\nkaputt\n", encoding="utf-8")
    s = verkaeufe(tmp_path, date(2026, 11, 5))
    assert s["count"] == 2 and s["photos"] == 3 and s["amount_cents"] == 2100
    assert s["by_method"]["card"] == {"count": 1, "amount_cents": 1200}
    seit = datetime.fromisoformat("2026-11-05T14:00:00+01:00").timestamp()
    neu = letzte_verkaeufe(tmp_path, seit, jetzt=datetime.fromisoformat("2026-11-05T15:00:00+01:00").timestamp())
    assert [v["id"] for v in neu] == ["a2"]
    assert neu[0]["codes"] == ["4456000000000002", "4456000000000003"]


def test_kiosk_ist_fernschaltbar():
    env = config_to_env({"park_slug": "x", "park_id": "p", "machine_id": "m",
                         "settings": {"kiosk_enabled": True, "kiosk_valid_until": "2027-03-31",
                                      "kiosk_config": {"edition": "card"}}}, "token")
    assert env["KIOSK_ENABLED"] == "true"
    assert env["KIOSK_VALID_UNTIL"] == "2027-03-31"
    assert json.loads(env["KIOSK_CONFIG_JSON"]) == {"edition": "card"}


def _dienst(tmp_path, **extra):
    import uuid
    basis = tmp_path / uuid.uuid4().hex[:8]
    basis.mkdir()
    settings = replace(make_settings(basis), kiosk_dir=tmp_path / "kiosk-data",
                       presentation_dir=None, file_code_positions="3,4,5,6", **extra)
    return LiftpicService(settings)


def test_lizenz_aus_dem_crm(tmp_path: Path):
    assert _dienst(tmp_path, kiosk_enabled=False)._kiosk_license() == (False, "disabled")
    an = _dienst(tmp_path, kiosk_enabled=True, kiosk_valid_until="2026-11-30")
    assert an._kiosk_license(heute=date(2026, 11, 30)) == (True, "")
    assert an._kiosk_license(heute=date(2026, 12, 1)) == (False, "expired")
    assert _dienst(tmp_path, kiosk_enabled=True, device_token="")._kiosk_license() == (False, "not_paired")
    offline = _dienst(tmp_path, kiosk_enabled=True)
    offline._config_ok_at = time.time() - 8 * 86400
    assert offline._kiosk_license() == (False, "offline")


def test_dienst_schreibt_nur_mit_freischaltung(tmp_path: Path):
    aus = _dienst(tmp_path, kiosk_enabled=False)
    aus._kiosk_if_due()
    assert not (tmp_path / "kiosk-data").exists()
    assert aus._kiosk_status() is None

    an = _dienst(tmp_path, kiosk_enabled=True)
    jetzt = datetime.now()
    _fotos(an.settings.raw_dir, ["I00057.JPG"], datetime.fromtimestamp(jetzt.timestamp() - 600))
    an._kiosk_if_due()
    d = _daten(tmp_path / "kiosk-data")
    assert d["licensed"] is True and d["photos"][0]["number"] == "0057"
    status = an._kiosk_status()
    assert status["licensed"] is True and status["photos"] == 1 and status["running"] is False
    assert status["sales_today"]["count"] == 0
