"""Liftpictures Presentation: Nachbau der Praesentation mit echten Kauf-Links."""
import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from liftpic_sync.presentation import Praesentation, abholcode, claim_basis, stil
from liftpic_sync.presentation_page import PAGE
from liftpic_sync.qr import qr_svg
from liftpic_sync.remote_config import config_to_env
from liftpic_sync.service import LiftpicService

from test_service import make_settings

SETTINGS_XML = """<?xml version="1.0"?>
<Settings>
  <QrCodeBeginningString>https://liftpictures-fotos.de/kalahari-virginia/claim?code=</QrCodeBeginningString>
  <QrCodeEndingString></QrCodeEndingString>
  <SplitNumberColumns>3</SplitNumberColumns>
  <SplitNumberRows>2</SplitNumberRows>
  <SplitBackgroundColor>#3977BD</SplitBackgroundColor>
  <SplitTickerText>Scan your photo..!</SplitTickerText>
  <SplitPreviewLogo>{logo}</SplitPreviewLogo>
</Settings>
"""


def _fotos(ordner: Path, namen: list[str], tag=datetime(2026, 11, 4, 9, 40)) -> None:
    ordner.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(namen):
        datei = ordner / name
        datei.write_bytes(b"\xff\xd8\xff\xd9")
        t = tag.timestamp() + 120 * i
        os.utime(datei, (t, t))


def _stand(ordner: Path) -> dict:
    text = (ordner / "photos.js").read_text(encoding="utf-8")
    return json.loads(text[len("window.__presentation&&window.__presentation("):-3])


def test_code_ist_derselbe_wie_beim_hochladen():
    """I00057 vom 04.11.2026 ist online als 4456006171002127 hinterlegt
    (live geprueft: der Link oeffnet genau dieses Foto)."""
    bild = Path("I00057.JPG")
    mtime = datetime(2026, 11, 4, 9, 44).timestamp()
    assert abholcode("4761", bild, "3,4,5,6", mtime) == "4456006171002127"


def test_stil_liest_die_split_werte_und_hat_die_vorgaben_des_originals():
    s = stil({"SplitNumberColumns": "4", "SplitBackgroundColor": "#112233", "SplitShowLabel": "false"})
    assert s["columns"] == 4 and s["background"] == "#112233" and s["show_label"] is False
    v = stil(None)
    assert (v["columns"], v["rows"], v["border"], v["ticker_text"]) == (3, 2, 20, "Scan your photo..!")


def test_alte_jpeg4web_adresse_wird_nicht_benutzt():
    alt = {"QrCodeBeginningString": "www2.liftpictures.de/jpeg4web/frame/preview.php?code="}
    assert claim_basis(alt, "kalahari-virginia") == ("https://liftpictures-fotos.de/kalahari-virginia/claim?code=", "")


def test_schreibt_raster_mit_neuestem_foto_zuerst_und_echtem_link(tmp_path: Path):
    fotos = tmp_path / "fotos"
    _fotos(fotos, [f"I000{n}.JPG" for n in range(50, 58)])  # 8 Fotos, Raster hat 6 Plaetze
    logo = tmp_path / "copy.png"
    logo.write_bytes(b"\x89PNG")
    xml = tmp_path / "Settings.xml"
    xml.write_text(SETTINGS_XML.format(logo=logo), encoding="latin-1")

    ziel = tmp_path / "presentation"
    p = Praesentation(ziel)
    assert p.schreibe(raw_dir=fotos, viewer_xml=xml, customer_code="4761", positionen="3,4,5,6",
                      park_slug="kalahari-virginia", lizenziert=True,
                      jetzt=datetime(2026, 11, 4, 12, 0).timestamp())
    stand = _stand(ziel)
    nummern = [f["number"] for f in stand["photos"]]
    assert nummern == ["0057", "0056", "0055", "0054", "0053", "0052"]
    erstes = stand["photos"][0]
    assert erstes["url"] == "https://liftpictures-fotos.de/kalahari-virginia/claim?code=" + erstes["code"]
    assert erstes["time"] == "09:54"
    assert erstes["qr"].startswith("<svg") and "path" in erstes["qr"]
    assert (ziel / "preview-logo.png").read_bytes() == b"\x89PNG"
    assert stand["style"]["viewer_logo"].startswith("preview-logo.png")
    assert stand["style"]["preset"] == "classic" and stand["style"]["background"] == "#3977BD"
    assert "__PAGE_REV__" not in (ziel / "index.html").read_text(encoding="utf-8")

    # Unveraendert -> nichts schreiben.
    assert not p.schreibe(raw_dir=fotos, viewer_xml=xml, customer_code="4761", positionen="3,4,5,6",
                          park_slug="kalahari-virginia", lizenziert=True,
                          jetzt=datetime(2026, 11, 4, 12, 0).timestamp())


def test_ohne_freischaltung_keine_fotos(tmp_path: Path):
    fotos = tmp_path / "fotos"
    _fotos(fotos, ["I00057.JPG"])
    ziel = tmp_path / "presentation"
    Praesentation(ziel).schreibe(raw_dir=fotos, viewer_xml=None, customer_code="4761", positionen="3,4,5,6",
                                 park_slug="kalahari-virginia", lizenziert=False,
                                 jetzt=datetime(2026, 11, 4, 12, 0).timestamp())
    stand = _stand(ziel)
    assert stand["licensed"] is False and stand["photos"] == []


def test_datei_die_gerade_geschrieben_wird_erscheint_noch_nicht(tmp_path: Path):
    fotos = tmp_path / "fotos"
    _fotos(fotos, ["I00057.JPG"], tag=datetime(2026, 11, 4, 12, 0))
    ziel = tmp_path / "presentation"
    Praesentation(ziel).schreibe(raw_dir=fotos, viewer_xml=None, customer_code="4761", positionen="3,4,5,6",
                                 park_slug="kalahari-virginia", lizenziert=True,
                                 jetzt=datetime(2026, 11, 4, 12, 0).timestamp() + 0.5)
    assert _stand(ziel)["photos"] == []


def test_qr_svg_hat_rand_und_quadratische_flaeche():
    svg = qr_svg("https://liftpictures-fotos.de/kalahari-virginia/claim?code=4456006171002127", border=2)
    # Version 4 = 33 Module + 2x2 Rand
    assert 'viewBox="0 0 37 37"' in svg


def test_presentation_ist_fernschaltbar():
    env = config_to_env({"park_slug": "x", "park_id": "p", "machine_id": "m",
                         "settings": {"presentation_enabled": True}}, "token")
    assert env["PRESENTATION_ENABLED"] == "true"


def test_dienst_schreibt_presentation_nur_mit_freischaltung(tmp_path: Path):
    settings = make_settings(tmp_path)
    _fotos(settings.raw_dir, ["I00057.JPG"])
    ziel = tmp_path / "presentation"
    aus = LiftpicService(replace(settings, presentation_dir=ziel, presentation_enabled=False))
    aus._presentation_if_due()
    assert not ziel.exists()

    an = LiftpicService(replace(settings, presentation_dir=ziel, presentation_enabled=True,
                                file_code_positions="3,4,5,6"))
    an._presentation_if_due()
    stand = _stand(ziel)
    assert stand["licensed"] is True and stand["photos"][0]["number"] == "0057"


def test_seite_braucht_kein_internet():
    assert "http://" not in PAGE and "https://" not in PAGE


# ------------------------------------------------------------------ Lizenz

def _dienst(tmp_path, **extra):
    import uuid
    basis = tmp_path / uuid.uuid4().hex[:8]
    basis.mkdir()
    settings = replace(make_settings(basis), presentation_dir=tmp_path / "presentation",
                       file_code_positions="3,4,5,6", **extra)
    return LiftpicService(settings)


def test_lizenz_aus_dem_crm(tmp_path: Path):
    from datetime import date
    assert _dienst(tmp_path, presentation_enabled=False)._presentation_license() == (False, "disabled")
    an = _dienst(tmp_path, presentation_enabled=True, license_valid_until="2026-11-30")
    assert an._presentation_license(heute=date(2026, 11, 30)) == (True, "")
    assert an._presentation_license(heute=date(2026, 12, 1)) == (False, "expired")
    assert _dienst(tmp_path, presentation_enabled=True, device_token="")._presentation_license() == (False, "not_paired")


def test_lizenz_endet_nach_sieben_tagen_ohne_serverkontakt(tmp_path: Path):
    import time
    svc = _dienst(tmp_path, presentation_enabled=True)
    svc._config_ok_at = time.time() - 6 * 86400
    assert svc._presentation_license()[0] is True
    svc._config_ok_at = time.time() - 8 * 86400
    assert svc._presentation_license() == (False, "offline")


def test_abgelaufene_lizenz_zeigt_hinweis_statt_fotos(tmp_path: Path):
    svc = _dienst(tmp_path, presentation_enabled=True, license_valid_until="2020-01-01")
    _fotos(svc.settings.raw_dir, ["I00057.JPG"])
    svc._presentation_if_due()
    stand = _stand(tmp_path / "presentation")
    assert stand["licensed"] is False and stand["reason"] == "expired" and stand["photos"] == []
    status = svc._presentation_status()
    assert status["licensed"] is False and status["reason"] == "expired"


def test_qr_link_aus_dem_crm_ueberschreibt_die_settings(tmp_path: Path):
    svc = _dienst(tmp_path, presentation_enabled=True,
                  presentation_qr_base="https://liftpictures-fotos.de/anderer-park/claim?code=")
    _fotos(svc.settings.raw_dir, ["I00057.JPG"])
    svc._presentation_if_due()
    url = _stand(tmp_path / "presentation")["photos"][0]["url"]
    assert url.startswith("https://liftpictures-fotos.de/anderer-park/claim?code=")


def test_fremder_qr_link_wird_ignoriert():
    assert claim_basis(None, "kalahari-virginia", "https://evil.example/claim?code=")[0] \
        == "https://liftpictures-fotos.de/kalahari-virginia/claim?code="


def test_lizenzfelder_sind_fernschaltbar():
    env = config_to_env({"park_slug": "x", "park_id": "p", "machine_id": "m", "settings": {
        "license_valid_until": "2026-12-31",
        "presentation_qr_base": "https://liftpictures-fotos.de/x/claim?code="}}, "token")
    assert env["LICENSE_VALID_UNTIL"] == "2026-12-31"
    assert env["PRESENTATION_QR_BASE"] == "https://liftpictures-fotos.de/x/claim?code="


# -------------------------------------------------------------- Gestaltung

def test_gestaltung_vorlage_und_eigene_werte():
    from liftpic_sync.presentation_design import gestaltung
    basis = stil(None)
    g = gestaltung(basis, {"preset": "signature", "radius": 99, "background": "#123456",
                           "layout": "spotlight", "ticker_messages": ["A", "", 5, "B"], "unbekannt": 1,
                           "time_format": "12h", "logo_url": "http://unsicher"})
    assert g["preset"] == "signature" and g["header"] is True       # aus der Vorlage
    assert g["radius"] == 48                                          # auf die Grenze gekappt
    assert g["background"] == "#123456" and g["layout"] == "spotlight"
    assert g["ticker_messages"] == ["A", "B"]                         # nur Texte
    assert g["logo_url"] == "" and "unbekannt" not in g              # nur https, nur bekannte Felder
    assert gestaltung(basis, {"layout": "kaputt"})["layout"] == "grid"


def test_design_kommt_per_fernkonfiguration_als_json():
    env = config_to_env({"park_slug": "x", "park_id": "p", "machine_id": "m",
                         "settings": {"presentation_design": {"preset": "signature", "background": "#002858"}}}, "t")
    assert json.loads(env["PRESENTATION_DESIGN_JSON"]) == {"preset": "signature", "background": "#002858"}


def test_karussell_holt_mehr_fotos(tmp_path: Path):
    fotos = tmp_path / "fotos"
    _fotos(fotos, [f"I000{n}.JPG" for n in range(10, 30)])
    ziel = tmp_path / "presentation"
    Praesentation(ziel).schreibe(raw_dir=fotos, viewer_xml=None, customer_code="4761", positionen="3,4,5,6",
                                 park_slug="kalahari-virginia", lizenziert=True,
                                 design={"layout": "carousel", "max_photos": 12},
                                 jetzt=datetime(2026, 11, 4, 12, 0).timestamp())
    stand = _stand(ziel)
    assert len(stand["photos"]) == 12 and stand["photos"][0]["ts"] > stand["photos"][1]["ts"]
