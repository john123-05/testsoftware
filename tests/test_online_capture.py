from dataclasses import replace
import json
import pytest
from liftpic_sync.filename_codec import viewer_file_code
from liftpic_sync.scanner import FolderScanner
from liftpic_sync.state import StateStore
from liftpic_sync.test_photo_upload import baue_metadaten
from liftpic_sync.camera_streams import stream_settings
from test_scanner import make_settings

def test_samuel_positions_include_the_canon_prefix():
    assert viewer_file_code('I00006.JPG', '3,4,5,6') == '0006'
    assert viewer_file_code('I00161.JPG', '3,4,5,6') == '0161'
    with pytest.raises(ValueError):
        viewer_file_code('IMG_0006.JPG', '3,4,5,6')

def test_online_inventory_and_manual_test_produce_the_same_code(tmp_path):
    s = replace(make_settings(tmp_path), upload_source='online', customer_code='4761',
                file_code_positions='3,4,5,6')
    image=s.raw_dir/'I00006.JPG';image.write_bytes(b'canon photo')
    # Ignore exported/processed copies, even if they have another capture number.
    (s.processed_dir/'I00007.JPG').write_bytes(b'not the online source')
    store=StateStore(s.state_db)
    assert FolderScanner(s,store).scan_once().queued == 1
    row=store.conn.execute('select * from photo_events').fetchone()
    metadata=json.loads(row['metadata_json'])
    test_name,test_metadata=baue_metadaten(s,image)
    assert metadata['legacy_filename']==test_name
    assert metadata['file_code']=='0006'
    assert metadata['speed_kmh'] is None
    assert metadata['speed_status']=='not_requested'
    assert metadata['sold_source_path'] is None
    assert test_metadata['is_test'] is True
    assert test_metadata['captured_at'][-6] in ('+','-')

def test_online_stream_survives_remote_config_refresh(tmp_path):
    base=make_settings(tmp_path)
    c={'machine_id':base.machine_id,'park_id':base.park_id,'camera_code':'canon',
       'legacy_customer_code':'4761','raw_dir':str(base.raw_dir),'processed_dir':str(base.raw_dir),
       'mode':'all_photos','shadow_mode':False,'settings':{'online_sales':True,'file_code_positions':'3,4,5,6'}}
    from liftpic_sync.remote_config import config_to_env
    assert config_to_env(c,'token')['UPLOAD_SOURCE']=='online'
    stream=stream_settings(replace(base,shadow_mode=False,camera_streams_json=json.dumps([c])))[0]
    assert stream.upload_source=='online'
    assert stream.file_code_positions=='3,4,5,6'
