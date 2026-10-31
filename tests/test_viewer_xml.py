from pathlib import Path

from liftpic_sync.viewer_xml import lies_viewer, schreibe_viewer

XML = (
    "﻿<Settings>\r\n  <CustomerNumber>3344</CustomerNumber>\r\n"
    "  <QrCodeBeginningString>www2.liftpictures.de/jpeg4web/frame/preview.php?code=</QrCodeBeginningString>\r\n"
    "  <EnableQrCodePrintButtons>false</EnableQrCodePrintButtons>\r\n"
    "  <PricePrint>5</PricePrint>\r\n  <Name>Schöne Grüße</Name>\r\n</Settings>\r\n"
)


def _datei(tmp_path: Path) -> Path:
    p = tmp_path / "Settings.xml"
    p.write_bytes(XML.encode("utf-8"))
    return p


def test_lesen(tmp_path):
    werte = lies_viewer(_datei(tmp_path))
    assert werte == {
        "QrCodeBeginningString": "www2.liftpictures.de/jpeg4web/frame/preview.php?code=",
        "EnableQrCodePrintButtons": False,
        "PricePrint": "5",
    }


def test_schreiben_aendert_nur_die_werte(tmp_path):
    p = _datei(tmp_path)
    vorher = p.read_bytes()
    e = schreibe_viewer(p, {
        "QrCodeBeginningString": "https://liftpictures-fotos.de/thale/claim?code=",
        "EnableQrCodePrintButtons": True,
        "PricePrint": 4,
    })
    assert e.fehler is None and e.sicherung
    nachher = p.read_bytes()
    assert nachher.replace(
        b"https://liftpictures-fotos.de/thale/claim?code=", b"www2.liftpictures.de/jpeg4web/frame/preview.php?code="
    ).replace(b">true<", b">false<").replace(b">4<", b">5<") == vorher
    assert Path(e.sicherung).read_bytes() == vorher
    assert lies_viewer(p)["EnableQrCodePrintButtons"] is True


def test_fremde_ziele_und_schluessel_abgelehnt(tmp_path):
    p = _datei(tmp_path)
    e = schreibe_viewer(p, {"QrCodeBeginningString": "https://evil.example/?code=", "CustomerNumber": "9999"})
    assert e.fehler and not e.geschrieben
    assert set(e.abgelehnt) == {"QrCodeBeginningString", "CustomerNumber"}
    assert p.read_bytes() == XML.encode("utf-8")
