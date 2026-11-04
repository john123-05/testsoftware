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
    assert stand["style"]["preview_logo"].startswith("preview-logo.png")
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
