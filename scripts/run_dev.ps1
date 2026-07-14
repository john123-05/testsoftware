param(
  [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"
python -m liftpic_sync.cli --env $EnvFile run
