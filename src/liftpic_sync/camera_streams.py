"""Multiple cameras on one physical PC: one agent and one durable queue."""
from dataclasses import replace
import json
from pathlib import Path
import re
from .scanner import ScanResult
from .ride_tracker import RideScanResult

def stream_settings(settings):
    values=json.loads(settings.camera_streams_json)
    if not isinstance(values,list) or not 1<=len(values)<=4:
        raise ValueError('Invalid camera stream list')
    result=[]
    seen=set()
    for c in values:
        if c.get('machine_id')!=settings.machine_id or c.get('park_id')!=settings.park_id:
            raise ValueError('Camera belongs to another machine or park')
        code=c['camera_code']
        if code in seen or not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,69}',code):
            raise ValueError('Duplicate/invalid camera stream')
        seen.add(code)
        opts=c.get('settings') or {}
        result.append(replace(settings,camera_code=code,customer_code=c['legacy_customer_code'],
            raw_dir=Path(c['raw_dir']),processed_dir=Path(c['processed_dir']),
            qrcode_dir=Path(c['qrcode_dir']) if c.get('qrcode_dir') else None,qrcode_dir_2=None,
            statistic_file=Path(c['statistic_file']) if c.get('statistic_file') else None,
            upload_source='statistic' if c['mode']=='sold_via_statistic' else 'qrcode',
            shadow_mode=settings.shadow_mode or c.get('shadow_mode',True) or c['mode']=='count_only',
            ride_count_enabled=c.get('count_rides_enabled',True),ride_count_parity=opts.get('ride_count_parity','all'),
            file_code_positions=opts.get('file_code_positions','2,3,4,5'),viewer_profile=int(opts.get('viewer_profile') or 1),
            viewer_settings_xml=Path(opts['viewer_settings_xml']) if opts.get('viewer_settings_xml') else None))
    return result

class CombinedScanner:
    def __init__(self,workers): self.workers=workers
    def scan_once(self):
        rows=[w.scan_once() for w in self.workers]
        return ScanResult(*(sum(getattr(r,k) for r in rows) for k in ('queued','staged','skipped_unstable','skipped_unknown')))

class CombinedRides:
    def __init__(self,workers): self.workers=workers
    def scan_once(self):
        rows=[w.scan_once() for w in self.workers]
        return RideScanResult(*(sum(getattr(r,k) for r in rows) for k in ('seen','new','skipped_unstable','skipped_unknown')))
