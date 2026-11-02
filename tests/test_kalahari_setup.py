from dataclasses import replace
import pytest
from liftpic_sync import kalahari_setup
from liftpic_sync.config import Settings
from test_scanner import make_settings

def test_customer_setup_backs_up_and_changes_only_approved_viewer_fields(tmp_path,monkeypatch):
    base=make_settings(tmp_path)
    xml=tmp_path/'Settings.xml'
    original=f'''<Settings><CustomerNumber>4761</CustomerNumber><CodePositionsInFilename>3,4,5,6</CodePositionsInFilename><PhotoFolder>{base.raw_dir}</PhotoFolder><QrCodeBeginningString>old</QrCodeBeginningString><EnableQrCodeShare>false</EnableQrCodeShare><PriceQrCodeShare>0</PriceQrCodeShare><EnablePrint>true</EnablePrint><EnableEmail>false</EnableEmail><EnableCreditCardPayment>false</EnableCreditCardPayment><LogoFilename>old.png</LogoFilename><SinglePhotoLogoFilename>old.png</SinglePhotoLogoFilename><DefaultPhoto>old.png</DefaultPhoto><Unrelated>keep</Unrelated></Settings>'''
    xml.write_text(original)
    (base.raw_dir/'I00006.JPG').write_bytes(b'capture')
    logo=tmp_path/'assets'/'kalahari'/'tom-foolerys-logo.png';logo.parent.mkdir(parents=True);logo.write_bytes(b'logo')
    s=replace(base,park_id=kalahari_setup.PARK,machine_id='kalahari-va-ropes-01',customer_code='4761',viewer_settings_xml=xml)
    monkeypatch.setattr(Settings,'from_env_file',classmethod(lambda *args:s))
    assert kalahari_setup.prepare(tmp_path)['checked']
    assert xml.read_text()==original
    result=kalahari_setup.prepare(tmp_path,True)
    assert result['configured']
    assert '<CustomerNumber>4761</CustomerNumber>' in xml.read_text()
    assert '<CodePositionsInFilename>3,4,5,6</CodePositionsInFilename>' in xml.read_text()
    assert '<EnablePrint>false</EnablePrint>' in xml.read_text()
    assert '<EnableQrCodeShare>true</EnableQrCodeShare>' in xml.read_text()
    assert '<Unrelated>keep</Unrelated>' in xml.read_text()
    assert str(tmp_path/'liftpictures-kalahari-logo.png') in xml.read_text()
    assert (tmp_path/'liftpictures-kalahari-logo.png').read_bytes()==b'logo'
    from pathlib import Path
    assert Path(result['backup']).read_text()==original

def test_customer_setup_refuses_an_unrelated_park(tmp_path,monkeypatch):
    s=make_settings(tmp_path)
    monkeypatch.setattr(Settings,'from_env_file',classmethod(lambda *args:s))
    with pytest.raises(ValueError,match='only for the approved'):
        kalahari_setup.prepare(tmp_path,True)
