"""One-time assistant pairing. Device credentials never enter chat or reports."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import urllib.request
from .envfile import write_env_values
from .remote_config import config_to_env
from .viewer_settings import read_viewer_recipe
from .tls import open_url
BASE = 'https://kvpcwlcfgmsmarjtwpsx.supabase.co/functions/v1/liftpictures-mcp/install'

def request(action: str, payload: dict, token: str = '') -> dict:
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + '/' + action, data=json.dumps(payload).encode(), headers=headers, method='POST')
    with open_url(req, timeout=30) as response:
        return json.load(response)

def build_environment(response: dict) -> dict[str, str]:
    configs = response['configs']
    if not configs:
        raise ValueError('No machine configuration')
    primary = configs[0]
    if len({c['machine_id'] for c in configs}) != 1 or len({c['park_id'] for c in configs}) != 1:
        raise ValueError('Mixed machine configuration')
    values = config_to_env(primary, response['device_token'])
    values.update({'APP_DIR': r'C:\liftpic\liftpic-sync', 'PAIRING_CODE': '', 'SHADOW_MODE': 'true',
                   'VIEWER_RECIPE_ENABLED': 'false', 'VIEWER_PROFILE': str(primary.get('settings',{}).get('viewer_profile') or 1), 'ASSET_SYNC_ENABLED': 'false', 'VIEWER_RESTART_ENABLED': 'false',
                   'FILE_CODE_POSITIONS': str(primary.get('settings', {}).get('file_code_positions') or '2,3,4,5'),
                   'CAMERA_STREAMS_JSON': json.dumps(configs, ensure_ascii=True, separators=(',', ':'))})
    # Store only on the PC: the server never asks the model to handle this token.
    return values

def check_sources(configs: list[dict]) -> tuple[bool, bool, str | None]:
    sources_ok = True
    codes_ok = True
    viewer_hash = None
    for c in configs:
        for key in ('raw_dir', 'processed_dir'):
            sources_ok &= bool(c.get(key)) and Path(c[key]).is_dir()
        source_key = 'statistic_file' if c['mode'] == 'sold_via_statistic' else 'qrcode_dir'
        if c['mode'] not in ('count_only', 'all_photos'):
            sources_ok &= bool(c.get(source_key)) and Path(c[source_key]).exists()
        viewer = c.get('settings', {}).get('viewer_settings_xml')
        recipe = read_viewer_recipe(viewer, int(c.get('settings', {}).get('viewer_profile') or 1))
        codes_ok &= bool(recipe and recipe.customer_number == c['legacy_customer_code'] and recipe.code_positions == c.get('settings', {}).get('file_code_positions'))
        if viewer and Path(viewer).is_file():
            viewer_hash = hashlib.sha256(Path(viewer).read_bytes()).hexdigest()
    return bool(sources_ok), bool(codes_ok), viewer_hash

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--code', required=True)
    parser.add_argument('--install-dir', default=r'C:\liftpic\liftpic-sync')
    args = parser.parse_args()
    directory = Path(args.install_dir)
    session_file = directory / '.setup-session'
    if not session_file.exists():
        session_file.write_text(secrets.token_hex(32), encoding='ascii')
    session = session_file.read_text(encoding='ascii').strip()
    response = request('redeem', {'code': args.code, 'session': session})
    values = build_environment(response)
    values['SUPABASE_URL'] = 'https://kvpcwlcfgmsmarjtwpsx.supabase.co'
    values['SUPABASE_FUNCTIONS_URL'] = 'https://kvpcwlcfgmsmarjtwpsx.supabase.co/functions/v1'
    write_env_values(directory / '.env', values)
    source_ok, code_ok, viewer_hash = check_sources(response['configs'])
    report = {'installation_id': response['installation_id'], 'source_paths_verified': source_ok,
              'code_matches': code_ok, 'viewer_sha256': viewer_hash}
    (directory / 'setup-check.json').write_text(json.dumps(report), encoding='utf-8')
    print(json.dumps(report))

if __name__ == '__main__':
    main()
