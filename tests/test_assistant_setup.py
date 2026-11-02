from dataclasses import replace
import json
from pathlib import Path
import os
import shutil
import subprocess
import pytest
from liftpic_sync.assistant_setup import build_environment, check_sources
from liftpic_sync.camera_streams import stream_settings
from liftpic_sync.config import Settings
from liftpic_sync.state import StateStore
from liftpic_sync.scanner import FolderScanner
from liftpic_sync.uploader import UploadWorker

def config(root, code='0123', camera='cam-one'):
    raw=root/camera;out=raw/'out';qr=raw/'qrcode'
    out.mkdir(parents=True);qr.mkdir()
    xml=root/(camera+'.xml');xml.write_text(f'<Settings><CustomerNumber>{code}</CustomerNumber><CodePositionsInFilename>2,3,4,5</CodePositionsInFilename></Settings>')
    return {'id':camera,'park_id':'park','park_slug':'park-slug','machine_id':'pc-one','camera_code':camera,'legacy_customer_code':code,'mode':'sold_only','shadow_mode':True,
        'raw_dir':str(raw),'processed_dir':str(out),'qrcode_dir':str(qr),'settings':{'viewer_settings_xml':str(xml),'file_code_positions':'2,3,4,5'}}

def test_pairing_values_keep_leading_zeroes_no_reusable_pairing_secret(tmp_path):
    c=config(tmp_path)
    v=build_environment({'configs':[c],'device_token':'test-token'})
    assert v['CUSTOMER_CODE']=='0123'
    assert v['PAIRING_CODE']=='' and v['SHADOW_MODE']=='true'
    assert v['VIEWER_RESTART_ENABLED']=='false'
    assert 'test-token' not in v['CAMERA_STREAMS_JSON']
    assert check_sources([c])[:2]==(True,True)
    Path(c['settings']['viewer_settings_xml']).write_text('<CustomerNumber>9999</CustomerNumber>')
    assert check_sources([c])[1] is False

def test_multiple_cameras_preserve_individual_codes_and_shadow_gate(tmp_path):
    one=config(tmp_path,camera='cam-one');two=config(tmp_path,code='4567',camera='cam-two')
    env=tmp_path/'.env';env.write_text('PARK_ID=park\nMACHINE_ID=pc-one\nSHADOW_MODE=false\nCAMERA_STREAMS_JSON='+json.dumps([one,two])+'\n')
    streams=stream_settings(Settings.from_env_file(env))
    assert [s.customer_code for s in streams]==['0123','4567']
    assert all(s.shadow_mode for s in streams)
    two['park_id']='another-park';env.write_text('PARK_ID=park\nMACHINE_ID=pc-one\nCAMERA_STREAMS_JSON='+json.dumps([one,two])+'\n')
    with pytest.raises(ValueError):stream_settings(Settings.from_env_file(env))

def test_secondary_shadow_stream_cannot_upload_through_live_primary(tmp_path):
    one=config(tmp_path,camera='cam-one');two=config(tmp_path,code='4567',camera='cam-two')
    env=tmp_path/'.env';env.write_text('PARK_ID=park\nMACHINE_ID=pc-one\nCUSTOMER_CODE=0123\nSHADOW_MODE=false\nAPP_DIR='+str(tmp_path)+'\nFILE_STABLE_SECONDS=0\nCAMERA_STREAMS_JSON='+json.dumps([one,two])+'\n')
    base=Settings.from_env_file(env)
    second=stream_settings(base)[1]
    (second.qrcode_dir/'00001.jpg').write_bytes(b'photo')
    store=StateStore(base.state_db)
    try:
        FolderScanner(second,store).scan_once()
        worker=UploadWorker(base,store)
        worker.client.begin=lambda *a:pytest.fail('shadow stream reached network upload')
        assert worker.upload_due()==1
        row=store.conn.execute('select upload_status from photo_events').fetchone()
        assert row['upload_status']=='shadowed'
    finally:store.close()

def test_exporter_only_reports_allowed_fields_and_does_not_change_source(tmp_path):
    pwsh=os.environ.get('LIFTPIC_TEST_PWSH') or shutil.which('pwsh')
    if not pwsh:pytest.skip('PowerShell not available')
    root=tmp_path/'liftpic';viewer=root/'samuel_neu';viewer.mkdir(parents=True)
    xml=viewer/'Settings.xml';xml.write_text('<Settings><CustomerNumber>0123</CustomerNumber><PricePrint>5,50</PricePrint><Password>FAKE-SECRET-MUST-NOT-EXPORT</Password></Settings>')
    before=xml.read_bytes();out=tmp_path/'reports';out.mkdir()
    script=Path(__file__).parents[1]/'scripts'/'export_pc_diagnostic.ps1'
    subprocess.run([pwsh,'-NoProfile','-File',str(script),'-Roots',str(root),'-OutputDir',str(out)],check=True,capture_output=True)
    reports=list(out.glob('*.json'));assert len(reports)==1
    content=reports[0].read_text(encoding='utf-8-sig');data=json.loads(content)
    assert data['viewers'][0]['fields']['CustomerNumber']=='0123'
    assert data['viewers'][0]['fields']['PricePrint']=='5,50'
    assert 'FAKE-SECRET' not in content and 'Password' not in content
    assert xml.read_bytes()==before
