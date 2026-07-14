param(
  [Parameter(Mandatory = $true)]
  [string]$Tag
)

$ErrorActionPreference = "Stop"
git checkout $Tag
python -m pip install -e .
powershell -ExecutionPolicy Bypass -File scripts\restart_service.ps1
