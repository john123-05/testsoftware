"""Lesen und Schreiben der Kameraeinstellungen.

Die Schreibseite ist der heikelste Teil des ganzen Agenten: eine falsch
gesetzte Belichtung macht einen Betriebstag unbrauchbar und faellt niemandem
sofort auf. Diese Tests halten die Zusagen fest, auf die man sich verlassen
koennen muss - nicht nur, dass Schreiben klappt, sondern vor allem, wann es
zu Recht NICHT klappt.
"""

from pathlib import Path

import pytest

from liftpic_sync import camera_settings as cs


VORLAGE = '''<device_state libver="3.4" filemajor="1" fileminor="0">
  <device name="DFK 33GX545 [Imst]" base_name="DFK 33GX545 [Imst]" unique_name="DFK 33GX545 [Imst] 42320366">
    <videoformat>YUY2 (4096x3000)</videoformat>
    <fps>4.75</fps>
    <vcdpropertyitems>
      <item guid="{A}" name="Saturation">
        <element guid="{B}" name="Value"><itf guid="{C}" value="120.3125" /></element>
      </item>
      <item guid="{D}" name="Gamma">
        <element guid="{E}" name="Value"><itf guid="{F}" value="0.81" /></element>
      </item>
      <item guid="{G}" name="Exposure">
        <element guid="{H}" name="Auto"><itf guid="{I}" value="1" /></element>
        <element guid="{J}" name="Value"><itf guid="{K}" value="0.001484" /></element>
      </item>
      <item guid="{L}" name="GPIO">
        <element guid="{M}" name="Read"><itf guid="{N}" value="7" /></element>
      </item>
    </vcdpropertyitems>
  </device>
</device_state>
'''


@pytest.fixture()
def xml(tmp_path: Path) -> Path:
    datei = tmp_path / "trigger.xml"
    datei.write_text(VORLAGE, encoding="utf-8")
    return datei


# --- Lesen ----------------------------------------------------------------

def test_liest_geraet_und_werte(xml):
    k = cs.lies_kamera(xml, programm="3gerTis_v70.exe")
    assert k.modell == "DFK 33GX545"
    assert k.seriennummer == "42320366"
    assert k.videoformat == "YUY2 (4096x3000)"
    assert k.werte["Saturation"]["Value"] == 120.3125
    assert k.werte["Exposure"]["Auto"] == 1


def test_uninteressantes_bleibt_draussen(xml):
    """GPIO gehoert nicht auf eine Bedienseite."""
    assert "GPIO" not in cs.lies_kamera(xml).werte


def test_fehlende_datei_ist_ein_befund_kein_absturz(tmp_path):
    k = cs.lies_kamera(tmp_path / "gibtsnicht.xml")
    assert k.fehler and "gibt es nicht" in k.fehler


def test_kaputte_datei_stuerzt_nicht_ab(tmp_path):
    datei = tmp_path / "kaputt.xml"
    datei.write_text("<device_state>", encoding="utf-8")
    assert cs.lies_kamera(datei).fehler is not None


# --- Schreiben ------------------------------------------------------------

def test_schreibt_und_legt_sicherung_an(xml):
    e = cs.schreibe_werte(xml, {"Saturation.Value": 130})
    assert e.erfolgreich
    assert e.geschrieben == {"Saturation.Value": 130}
    assert e.sicherung and Path(e.sicherung).exists()
    assert cs.lies_kamera(xml).werte["Saturation"]["Value"] == 130
    # Die Sicherung haelt den alten Wert fest
    assert cs.lies_kamera(Path(e.sicherung)).werte["Saturation"]["Value"] == 120.3125


def test_alles_andere_bleibt_unangetastet(xml):
    """Nur das eine Attribut. GUIDs und fremde Eintraege ueberleben."""
    cs.schreibe_werte(xml, {"Gamma.Value": 1.2})
    text = xml.read_text(encoding="utf-8")
    assert 'name="GPIO"' in text
    assert 'value="7"' in text
    assert 'unique_name="DFK 33GX545 [Imst] 42320366"' in text


def test_wert_ausserhalb_der_grenzen_wird_abgelehnt(xml):
    e = cs.schreibe_werte(xml, {"Gamma.Value": 99})
    assert not e.erfolgreich
    assert "Gamma.Value" in e.abgelehnt
    # und die Datei ist unveraendert
    assert cs.lies_kamera(xml).werte["Gamma"]["Value"] == 0.81


def test_nicht_freigegebene_eigenschaft_wird_abgelehnt(xml):
    """GPIO steht nicht in SCHREIBBAR - auch nicht auf Zuruf."""
    e = cs.schreibe_werte(xml, {"GPIO.Read": 1})
    assert not e.erfolgreich
    assert e.abgelehnt["GPIO.Read"] == "darf aus der Ferne nicht geaendert werden"
    assert 'value="7"' in xml.read_text(encoding="utf-8")


def test_ohne_gueltigen_wert_keine_sicherung(xml):
    """Kein Muell im Ordner fuer Auftraege, die ohnehin abgelehnt werden."""
    cs.schreibe_werte(xml, {"Gamma.Value": 99})
    assert not list(xml.parent.glob("*.sicherung-*"))


def test_teils_gueltig_schreibt_nur_das_gueltige(xml):
    e = cs.schreibe_werte(xml, {"Saturation.Value": 110, "Gamma.Value": 99})
    assert e.geschrieben == {"Saturation.Value": 110}
    assert "Gamma.Value" in e.abgelehnt
    assert cs.lies_kamera(xml).werte["Gamma"]["Value"] == 0.81


def test_unbekannte_eigenschaft_dieser_kamera(tmp_path):
    """Freigegeben, aber diese Kamera kennt es nicht."""
    datei = tmp_path / "t.xml"
    datei.write_text(VORLAGE, encoding="utf-8")
    e = cs.schreibe_werte(datei, {"Denoise.Value": 5})
    assert not e.erfolgreich
    assert "Denoise.Value" in e.abgelehnt


def test_ganze_zahlen_ohne_komma(xml):
    """Die Kamera schreibt 1, nicht 1.0 - das bleibt so."""
    cs.schreibe_werte(xml, {"Exposure.Auto": 0})
    assert 'value="0"' in xml.read_text(encoding="utf-8")


def test_belichtung_in_sekunden(xml):
    e = cs.schreibe_werte(xml, {"Exposure.Value": 0.002})
    assert e.erfolgreich
    assert cs.lies_kamera(xml).werte["Exposure"]["Value"] == 0.002
