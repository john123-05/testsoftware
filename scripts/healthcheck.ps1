param(
  [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"
python -m liftpic_sync.cli health --env $EnvFile
