from __future__ import annotations
import argparse
import json
from pathlib import Path
from .assistant_setup import request
from .config import Settings

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--install-dir', default=r'C:\liftpic\liftpic-sync')
    args=parser.parse_args()
    directory=Path(args.install_dir)
    settings=Settings.from_env_file(directory / '.env')
    receipt=json.loads((directory / 'setup-receipt.json').read_text(encoding='utf-8-sig'))
    request('receipt', receipt, settings.device_token)
    print('Installationsbericht gespeichert.')

if __name__ == '__main__':
    main()
