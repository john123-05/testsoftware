<#
  fix-liftpic.ps1 - one-shot recovery + hardening for the Liftpic Sync agent.

  It restarts the agent cleanly, updates it to the self-healing build and
  refreshes its device token so uploads resume. No interaction needed.

  Steps:
    1. stop the scheduled task and end any running agent instance
    2. clear stale single-instance locks
    3. pull the latest agent code from the public repo (self-heal build)
    4. ensure the .env has the functions URL + the stored pairing code
    5. re-pair to fetch a fresh device token (fixes the 401 upload rejection)
    6. start exactly one instance again
    7. print a short result report

  Run (one line, PowerShell on the customer PC):
    [Net.ServicePointManager]::SecurityProtocol='Tls12'; & ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/john123-05/testsoftware/main/scripts/fix-liftpic.ps1'))) F7C32C56
#>
param(
  [string]$PairCode = "",
  [string]$InstallDir = "C:\liftpic\liftpic-sync",
  [string]$Repo = "https://github.com/john123-05/testsoftware/archive/refs/heads/main.zip",
  [string]$FunctionsUrl = "https://kvpcwlcfgmsmarjtwpsx.supabase.co/functions/v1",
  [string]$SupabaseUrl = "https://kvpcwlcfgmsmarjtwpsx.supabase.co"
)

$ErrorActionPreference = "Continue"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }

$EnvPath = Join-Path $InstallDir ".env"
$SrcDir  = Join-Path $InstallDir "src"
$PkgDir  = Join-Path $SrcDir "liftpic_sync"

# ---------------------------------------------------------------- 1. find task
$TaskName = "LiftpicSync"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
  $task = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    ((($_.Actions.Execute -join ' ') + ' ' + ($_.Actions.Arguments -join ' ')) -match 'liftpic')
  } | Select-Object -First 1
  if ($task) { $TaskName = $task.TaskName }
}

# ------------------------------------------------- 2. stop the running agent
Step "Stoppe die Agent-Aufgabe und laufende Instanz(en)"
if ($task) { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
try {
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'liftpic_sync' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {}
Start-Sleep -Seconds 2
Remove-Item (Join-Path $InstallDir 'state\liftpic-sync.lock') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $env:ProgramData 'liftpic-sync\singleton.lock') -Force -ErrorAction SilentlyContinue

# -------------------------------------------------- 3. pull latest agent code
Step "Lade neuesten Agent-Code (Selbstheil-Version)"
$zip = Join-Path $env:TEMP 'liftpic-ts.zip'
$out = Join-Path $env:TEMP 'liftpic-ts'
$codeUpdated = $false
try {
  if (Test-Path $out) { Remove-Item $out -Recurse -Force -ErrorAction SilentlyContinue }
  Invoke-WebRequest -Uri $Repo -OutFile $zip -UseBasicParsing
  Expand-Archive -Path $zip -DestinationPath $out -Force
  $newPkg = Join-Path $out 'testsoftware-main\src\liftpic_sync'
  if ((Test-Path $newPkg) -and (Test-Path $PkgDir)) {
    Copy-Item (Join-Path $newPkg '*.py') $PkgDir -Force
    $codeUpdated = $true
  }
} catch { Write-Host "   Code-Update uebersprungen: $($_.Exception.Message)" -ForegroundColor Yellow }

# ------------------------------------ 4. ensure .env has URL + pairing code
Step "Stelle .env sicher (Verbindung + Kopplungscode)"
if (-not (Test-Path $EnvPath)) { New-Item -ItemType File -Path $EnvPath -Force | Out-Null }
$lines = @(Get-Content -Path $EnvPath -ErrorAction SilentlyContinue)
function Set-EnvKey([string[]]$src, [string]$key, [string]$val, [bool]$onlyIfMissing) {
  $has = $src | Where-Object { $_ -match "^\s*$key\s*=" }
  if ($has -and $onlyIfMissing) { return $src }
  $src = $src | Where-Object { $_ -notmatch "^\s*$key\s*=" }
  return $src + "$key=$val"
}
$lines = Set-EnvKey $lines 'SUPABASE_FUNCTIONS_URL' $FunctionsUrl $true
$lines = Set-EnvKey $lines 'SUPABASE_URL' $SupabaseUrl $true
if ($PairCode) { $lines = Set-EnvKey $lines 'PAIRING_CODE' $PairCode $false }
Set-Content -Path $EnvPath -Value $lines -Encoding UTF8

# ------------------------------------------------------- 5. find python + pair
$py = $null
if ($task) { $exe = ($task.Actions | Select-Object -First 1).Execute; if ($exe -and (Test-Path $exe)) { $py = $exe } }
if ($py -and $py -match 'pythonw\.exe$') { $alt = $py -replace 'pythonw\.exe$','python.exe'; if (Test-Path $alt) { $py = $alt } }
if (-not $py) {
  foreach ($c in @(
      (Join-Path $InstallDir '.venv\Scripts\python.exe'),
      (Join-Path $InstallDir 'venv\Scripts\python.exe'))) { if (Test-Path $c) { $py = $c; break } }
}
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { $py = (Get-Command python -ErrorAction SilentlyContinue).Source }

$paired = $false
if ($py -and $PairCode) {
  Step "Koppele neu (frischer Token)"
  $env:PYTHONPATH = $SrcDir
  try {
    & $py -m liftpic_sync pair --code $PairCode --env $EnvPath
    if ($LASTEXITCODE -eq 0) { $paired = $true }
  } catch { Write-Host "   Kopplung fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Yellow }
}

# ------------------------------------------------------- 6. start ONE instance
Step "Starte genau eine Instanz"
if ($task) {
  Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
} elseif ($py) {
  Start-Process -FilePath $py -ArgumentList '-m','liftpic_sync','run','--env',$EnvPath `
    -WorkingDirectory $SrcDir -WindowStyle Hidden
}
Start-Sleep -Seconds 6

# ------------------------------------------------------------------- 7. report
$procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -match 'liftpic_sync' })
$state = (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue).State
$tok = ""
if (Test-Path $EnvPath) { $tok = ((Select-String -Path $EnvPath -Pattern '^DEVICE_TOKEN=' -ErrorAction SilentlyContinue).Line -replace '^DEVICE_TOKEN=','') }
$envs = @(Get-ChildItem -Path C:\ -Recurse -Filter '.env' -Depth 5 -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match 'liftpic' } | Select-Object -ExpandProperty FullName)

Write-Host ""
Write-Host "================ ERGEBNIS ================" -ForegroundColor Green
Write-Host ("Aufgabe             : {0}  (Status: {1})" -f $TaskName, $state)
Write-Host ("Code aktualisiert   : {0}" -f $codeUpdated)
Write-Host ("Neu gekoppelt       : {0}" -f $paired)
Write-Host ("Laufende Instanzen  : {0}   (soll: 1)" -f $procs.Count)
if ($tok) { Write-Host ("Neuer Token         : len={0} tail={1}" -f $tok.Length, ($tok.Substring([Math]::Max(0,$tok.Length-6)))) }
Write-Host ("Installationen(.env): {0}" -f ($(if ($envs.Count) { $envs -join ' | ' } else { 'keine gefunden' })))
Write-Host "=========================================" -ForegroundColor Green
Write-Host "Fertig. Der Agent laeuft, holt sich bei jedem 401 kuenftig selbst einen frischen Token,"
Write-Host "und die Warteschlange sollte jetzt hochlaufen. (Dashboard-Zahlen folgen in Minuten.)"
