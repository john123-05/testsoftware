$ErrorActionPreference = "Stop"

python -m pip install -e ".[build]"
python -m PyInstaller --onefile --name liftpic-sync --console src\liftpic_sync\cli.py

Write-Host "Built dist\liftpic-sync.exe"
