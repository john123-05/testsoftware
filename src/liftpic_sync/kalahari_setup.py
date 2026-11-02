"""The reviewed, customer-specific local setup for the Virginia Canon PC."""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path
from .config import Settings
from .viewer_settings import read_viewer_recipe
from .viewer_xml import lies_alle, schreibe_viewer
from .filename_codec import viewer_file_code

PARK = 'cd65690a-3e83-414a-8e38-5482cfe1c482'
QR = 'https://liftpictures-fotos.de/kalahari-virginia/claim?code='

def prepare(root: Path, configure: bool = False):
    settings=Settings.from_env_file(root/'.env')
    if settings.park_id != PARK or settings.machine_id != 'kalahari-va-ropes-01' or settings.customer_code != '4761':
        raise ValueError('This setup is only for the approved Kalahari Virginia PC')
    viewer=settings.viewer_settings_xml
    recipe=read_viewer_recipe(viewer)
    if not recipe or recipe.customer_number!='4761' or recipe.code_positions!='3,4,5,6':
        raise ValueError('Samuel code recipe changed; aborting without editing it')
    values=lies_alle(viewer) or {}
    folder=str(values.get('PhotoFolder','')).rstrip('\\/').casefold()
    if folder != str(settings.raw_dir).rstrip('\\/').casefold():
        raise ValueError('Samuel photo folder differs from the approved capture folder')
    samples=list(settings.raw_dir.glob('I*.JPG')) + list(settings.raw_dir.glob('I*.jpg'))
    if not samples:
        raise ValueError('No Canon I00001.JPG sample in the approved folder')
    for image in samples[:20]:
        viewer_file_code(image.name,'3,4,5,6')
    logo=root/'assets'/'kalahari'/'tom-foolerys-logo.png'
    if not logo.is_file():
        raise ValueError('Reviewed Kalahari logo is missing')
    # The credential directory is restricted to SYSTEM/Administrators. Samuel
    # also runs as a normal user after reboot, so its public logo belongs beside Settings.xml.
    viewer_logo=Path(viewer).parent/'liftpictures-kalahari-logo.png'
    changes={'QrCodeBeginningString':QR,'EnableQrCodeShare':True,'PriceQrCodeShare':'0',
             'EnablePrint':False,'EnableEmail':False,'EnableCreditCardPayment':False,
             'LogoFilename':str(viewer_logo),'SinglePhotoLogoFilename':str(viewer_logo),'DefaultPhoto':str(viewer_logo)}
    if any(k not in values for k in changes):
        raise ValueError('Expected Samuel settings are missing; no partial changes allowed')
    if not configure:
        return {'checked':True,'customer_code':'4761','source':str(settings.raw_dir),'qr_target':QR}
    shutil.copyfile(logo,viewer_logo)
    result=schreibe_viewer(viewer,changes)
    if result.fehler or result.abgelehnt:
        raise ValueError('Samuel configuration could not be updated completely')
    report={'configured':True,'customer_code':'4761','qr_target':QR,'backup':result.sicherung,
            'local_payments':False,'online_test_price_cents':500,'currency':'USD'}
    (root/'kalahari-setup.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--install-dir',default=r'C:\liftpic\liftpic-sync');parser.add_argument('--configure-viewer',action='store_true')
    args=parser.parse_args();print(json.dumps(prepare(Path(args.install_dir),args.configure_viewer)))

if __name__=='__main__':main()
