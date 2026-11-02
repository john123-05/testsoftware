"""Upload one explicitly selected local test photo; no revenue and no camera control."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from .assistant_setup import request
from .camera_streams import stream_settings
from .config import Settings
from .supabase_client import SupabaseIngestClient
from .test_photo_upload import baue_metadaten

def main():
    p=argparse.ArgumentParser();p.add_argument('--installation-id',required=True);p.add_argument('--install-dir',default=r'C:\liftpic\liftpic-sync');args=p.parse_args()
    root=Path(args.install_dir);base=Settings.from_env_file(root/'.env');streams=stream_settings(base)
    print('Kameras: '+', '.join(s.camera_code for s in streams))
    camera=input('Kamera-Code (Enter bei nur einer Kamera): ').strip()
    if not camera and len(streams)==1:camera=streams[0].camera_code
    stream=next((s for s in streams if s.camera_code==camera),None)
    if stream is None:raise ValueError('Kamera nicht gefunden')
    print('Erlaubte Bildordner: '+', '.join(str(p) for p in [stream.raw_dir,stream.processed_dir,stream.qrcode_dir] if p))
    image=Path(input('Vollstaendiger Pfad des gerade aufgenommenen Testbilds: ').strip().strip('"')).resolve()
    allowed={p.resolve() for p in [stream.raw_dir,stream.processed_dir,stream.qrcode_dir] if p}
    if image.parent not in allowed or image.suffix.lower() not in ('.jpg','.jpeg') or not image.is_file():raise ValueError('Testbild nicht in bestaetigtem Kameraordner')
    if input('Genau dieses Bild als Testfoto hochladen (JA): ').strip()!='JA':raise ValueError('Abgebrochen')
    _,metadata=baue_metadaten(stream,image);metadata['customer_code']=stream.customer_code
    client=SupabaseIngestClient(base);upload=client.begin(metadata,image.stat().st_size)['upload']
    if '/testfoto/' not in upload['storage_path']:raise ValueError('Server hat keinen Testpfad geliefert')
    client.upload_signed(bucket=upload.get('bucket'),storage_path=upload['storage_path'],token=upload.get('token'),signed_url=upload.get('signed_url'),path=image)
    client.commit(metadata['capture_id'],upload['storage_path'],event_key=metadata['event_key'])
    result=request('test-receipt',{'installation_id':args.installation_id,'event_key':metadata['event_key']},base.device_token)
    print('Testfoto gespeichert, kein Umsatz. Gedruckten Code jetzt mit diesem Code vergleichen: '+str(result['external_code']))
    print('Anschliessend QR am Ausdruck auf der richtigen Parkseite pruefen. Ergebnis im CRM bestaetigen.')
if __name__=='__main__':main()
