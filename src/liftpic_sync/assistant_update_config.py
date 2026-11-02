from __future__ import annotations
import argparse
import json
from pathlib import Path
from .config import Settings
from .supabase_client import SupabaseIngestClient
from .envfile import write_env_values
from .assistant_setup import check_sources

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installation-id',required=True);parser.add_argument('--install-dir',default=r'C:\liftpic\liftpic-sync');args=parser.parse_args()
    root=Path(args.install_dir);settings=Settings.from_env_file(root/'.env')
    response=SupabaseIngestClient(settings).fetch_config();config=response['config']
    streams=config.get('settings',{}).get('camera_streams') or []
    if not streams:raise ValueError('No approved camera configuration on server')
    # The established primary source remains local unless deliberately changed separately.
    for c in streams:
        if c['camera_code']==settings.camera_code:
            c.update({'raw_dir':str(settings.raw_dir),'processed_dir':str(settings.processed_dir),'qrcode_dir':str(settings.qrcode_dir) if settings.qrcode_dir else '',
                      'statistic_file':str(settings.statistic_file) if settings.statistic_file else '', 'legacy_customer_code':settings.customer_code})
            c['settings']['file_code_positions']=settings.file_code_positions
            c['settings']['viewer_settings_xml']=str(settings.viewer_settings_xml) if settings.viewer_settings_xml else None
    write_env_values(root/'.env',{'CAMERA_STREAMS_JSON':json.dumps(streams,ensure_ascii=True,separators=(',',':'))})
    source_ok,code_ok,viewer_hash=check_sources(streams)
    (root/'setup-check.json').write_text(json.dumps({'installation_id':args.installation_id,'source_paths_verified':source_ok,'code_matches':code_ok,'viewer_sha256':viewer_hash}),encoding='utf-8')
    print('Konfiguration gelesen; bestehendes Geraetetoken und lokale Hauptpfade erhalten.')
if __name__=='__main__':main()
