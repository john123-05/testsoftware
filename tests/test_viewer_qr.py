"""QR-Umstellung aus dem CRM (W5): nur erlaubte Ziele, nur zwei Felder, Datei sonst unveraendert."""
from datetime import datetime

from liftpic_sync.viewer_qr import apply_qr, plane_aenderung, url_erlaubt

XML = (
    "﻿<?xml version=\"1.0\"?>\r\n<Settings>\r\n"
    "  <CustomerNumber>2734</CustomerNumber>\r\n"
    "  <QrCodeBeginningString>https://liftpictures-fotos.de/imst/claim?code=</QrCodeBeginningString>\r\n"
    "  <EnableQrCodePrintButtons>True</EnableQrCodePrintButtons>\r\n"
    "  <PricePrintWithQrCode>1000</PricePrintWithQrCode>\r\n"
    "</Settings>\r\n"
)


def test_erlaubte_urls():
    assert url_erlaubt("https://liftpictures-fotos.de/imst/claim?code=")
    assert url_erlaubt("https://www.liftpictures-fotos.de/x")
    for boese in (
        "http://liftpictures-fotos.de/x",            # kein https
        "https://liftpictures-fotos.de.evil.com/x",   # fremde Domain
        "https://evil.com/liftpictures-fotos.de",
        "https://user:pw@liftpictures-fotos.de/x",
        "https://liftpictures-fotos.de:8443/x",
        "https://liftpictures-fotos.de/x\"><b>",
        "javascript:alert(1)",
    ):
        assert not url_erlaubt(boese), boese


def test_nur_die_zwei_felder_aendern_sich():
    neu, e = plane_aenderung(XML, "https://liftpictures-fotos.de/serles/claim?code=", False)
    assert e.ok and e.changed
    assert "<QrCodeBeginningString>https://liftpictures-fotos.de/serles/claim?code=</QrCodeBeginningString>" in neu
    assert "<EnableQrCodePrintButtons>False</EnableQrCodePrintButtons>" in neu  # Schreibweise bleibt
    rest_alt = XML.replace("imst", "").replace("True", "")
    rest_neu = neu.replace("serles", "").replace("False", "")
    assert rest_alt == rest_neu  # CRLF, BOM und andere Felder identisch
    assert e.old_enabled is True and e.new_enabled is False


def test_fremde_url_wird_abgelehnt_und_nichts_geaendert():
    neu, e = plane_aenderung(XML, "https://evil.com/claim?code=", None)
    assert not e.ok and neu == XML


def test_fehlender_tag_wird_nicht_erfunden():
    ohne = XML.replace("  <EnableQrCodePrintButtons>True</EnableQrCodePrintButtons>\r\n", "")
    neu, e = plane_aenderung(ohne, None, True)
    assert not e.ok and "fehlt" in e.reason and neu == ohne


def test_gleicher_stand_ist_kein_schreiben(tmp_path):
    p = tmp_path / "Settings.xml"
    p.write_bytes(XML.encode("utf-8"))
    e = apply_qr(p, "https://liftpictures-fotos.de/imst/claim?code=", True)
    assert e.ok and not e.changed
    assert list(tmp_path.iterdir()) == [p]  # keine Sicherung, nichts geschrieben


def test_schreibt_mit_sicherung_und_behaelt_bom(tmp_path):
    p = tmp_path / "Settings.xml"
    p.write_bytes(XML.encode("utf-8"))  # XML beginnt mit ﻿ -> BOM in der Datei
    e = apply_qr(p, None, False, now=datetime(2026, 10, 30, 3, 0, 0))
    assert e.ok and e.changed
    sicherung = tmp_path / "Settings.xml.bak-qr-20261030-030000"
    assert sicherung.read_bytes() == XML.encode("utf-8")
    roh = p.read_bytes()
    assert roh.startswith(b"\xef\xbb\xbf") and b"\r\n" in roh
    assert b"<EnableQrCodePrintButtons>False</EnableQrCodePrintButtons>" in roh


def test_ohne_pfad_klare_ablehnung():
    e = apply_qr(None, None, True)
    assert not e.ok and "VIEWER_SETTINGS_XML" in e.reason
