param(
  [string]$PairingCode = "",
  [string]$InstallDir = "C:\liftpic\liftpic-sync",
  [string]$RepoZipUrl = "https://github.com/john123-05/testsoftware/archive/refs/heads/main.zip",
  [string]$SupabaseUrl = "https://kvpcwlcfgmsmarjtwpsx.supabase.co",
  [string]$SupabaseAnonKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt2cGN3bGNmZ21zbWFyanR3cHN4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1MDczODEsImV4cCI6MjA4NjA4MzM4MX0.KiMNRutSws--fAxKnSRJgmoq3UiqoyfPowKiPWVs-A0"
)

$ErrorActionPreference = "Stop"

function Assert-Admin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Bitte PowerShell als Administrator starten und diese Datei nochmal ausfuehren."
  }
}

function Get-Python {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) { return $python.Source }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) { return $py.Source }

  return $null
}

function Ensure-Python {
  $python = Get-Python
  if ($python) { return $python }

  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($winget) {
    Write-Host "Python nicht gefunden. Installiere Python 3.12 mit winget..."
    & $winget.Source install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $python = Get-Python
    if ($python) { return $python }
  }

  Start-Process "https://www.python.org/downloads/windows/"
  throw "Python konnte nicht automatisch installiert werden. Bitte Python 3.11 oder neuer installieren und diese Datei danach erneut starten."
}

function Get-EnvKeys {
  param([string]$EnvPath)

  $keys = New-Object System.Collections.Generic.HashSet[string]
  if (Test-Path $EnvPath) {
    foreach ($line in Get-Content -Path $EnvPath) {
      $trimmed = $line.Trim()
      if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
      $key = $trimmed.Split("=", 2)[0].Trim()
      if ($key) { [void]$keys.Add($key) }
    }
  }
  return $keys
}

function Set-EnvValue {
  param(
    [string]$EnvPath,
    [string]$Key,
    [string]$Value
  )

  $existing = @()
  if (Test-Path $EnvPath) { $existing = @(Get-Content -Path $EnvPath) }

  $pattern = "^\s*$([regex]::Escape($Key))\s*="
  $replaced = $false
  $output = foreach ($line in $existing) {
    if ($line -match $pattern) {
      $replaced = $true
      "$Key=$Value"
    } else {
      $line
    }
  }
  if (-not $replaced) { $output = @($output) + "$Key=$Value" }

  New-Item -ItemType Directory -Force -Path (Split-Path $EnvPath -Parent) | Out-Null
  Set-Content -Path $EnvPath -Value $output -Encoding ASCII
}

function Ensure-BaseEnv {
  param(
    [string]$EnvPath,
    [string]$BaseUrl,
    [string]$AnonKey
  )

  $functionsUrl = "$BaseUrl/functions/v1"
  $defaults = [ordered]@{
    APP_NAME                      = "liftpic-sync"
    SHADOW_MODE                   = "true"
    PARK_SLUG                     = "unknown-park"
    PARK_ID                       = ""
    CUSTOMER_CODE                 = "0000"
    MACHINE_ID                    = "unpaired-pc"
    CAMERA_CODE                   = "default"
    DEVICE_TOKEN                  = ""
    SUPABASE_FUNCTIONS_URL        = $functionsUrl
    SUPABASE_URL                  = $BaseUrl
    SUPABASE_ANON_KEY             = $AnonKey
    RAW_DIR                       = "C:\liftpic\fotos"
    PROCESSED_DIR                 = "C:\liftpic\fotos\out"
    WEBOUT_DIR                    = "C:\liftpic\fotos\webout"
    QRCODE_DIR                    = "C:\liftpic\fotos\qrcode"
    UPLOAD_SOURCE                 = "qrcode"
    STAGE_IN_SHADOW               = "false"
    STATISTIC_FILE                = "C:\liftpic\samuel_neu\Statistic.txt"
    PRINT_COUNT_FILE              = "C:\liftpic\samuel_neu\PrintCount.txt"
    APP_DIR                       = "C:\liftpic\liftpic-sync"
    STATE_DB                      = "C:\liftpic\liftpic-sync\state\liftpic-sync.db"
    LOG_DIR                       = "C:\liftpic\liftpic-sync\logs"
    POLL_SECONDS                  = "2"
    FILE_STABLE_SECONDS           = "2"
    SPEED_MATCH_SECONDS           = "12"
    SPEED_TIMEOUT_SECONDS         = "30"
    UPLOAD_RETRY_SECONDS          = "15"
    HEARTBEAT_SECONDS             = "60"
    CONFIG_REFRESH_SECONDS        = "120"
    ARCHIVE_RAW                   = "false"
    RIDE_COUNT_ENABLED            = "true"
    RIDE_COUNT_SOURCE             = "processed,raw"
    RIDE_ROLLUP_DAYS              = "14"
    ASSET_SYNC_ENABLED            = "false"
    ASSET_SYNC_SECONDS            = "300"
    ASSET_BACKUP_DIR              = "C:\liftpic\liftpic-sync\backups\assets"
    ASSET_SYNC_ALLOWED_ROOTS      = "C:\liftpic\samuel_neu;C:\liftpic\imageloader;C:\liftpic\jpeg4web"
    OPERATIONAL_LOG_GLOBS         = "C:\liftpic\imageloader\*.txt;C:\liftpic\imageloader\*.log;C:\liftpic\kosel\*.log;C:\liftpic\CAMware\log\*.txt;C:\liftpic\CAMware\*.log;C:\liftpic\3GerTis\*.log"
    OPERATIONAL_LOG_TAIL_LINES    = "80"
    OPERATIONAL_LOG_STALE_MINUTES = "240"
  }

  if (-not (Test-Path $EnvPath)) {
    Write-Host "Erstelle neue .env mit Grundeinstellungen..."
    $lines = foreach ($key in $defaults.Keys) { "$key=$($defaults[$key])" }
    New-Item -ItemType Directory -Force -Path (Split-Path $EnvPath -Parent) | Out-Null
    Set-Content -Path $EnvPath -Value $lines -Encoding ASCII
  }
  else {
    $existingKeys = Get-EnvKeys -EnvPath $EnvPath
    $missing = @($defaults.Keys | Where-Object { -not $existingKeys.Contains($_) })
    if ($missing.Count -eq 0) {
      Write-Host "Bestehende .env vorhanden, ergaenze fehlende Werte falls noetig."
    } else {
      Write-Host "Bestehende .env ist unvollstaendig. Ergaenze fehlende Werte: $($missing -join ', ')"
      $appendLines = foreach ($key in $missing) { "$key=$($defaults[$key])" }
      Add-Content -Path $EnvPath -Value $appendLines -Encoding ASCII
    }
  }

  # Always (re)write the fixed Supabase infrastructure values, even when a stale
  # .env already contains these keys with an empty or outdated value. Without
  # this, a broken .env (e.g. an empty "SUPABASE_FUNCTIONS_URL=") survives a
  # re-install - the completeness check only tests whether a key exists, not
  # whether it has a value - and pairing fails with
  # "SUPABASE_FUNCTIONS_URL is not configured".
  Set-EnvValue -EnvPath $EnvPath -Key "SUPABASE_URL" -Value $BaseUrl
  Set-EnvValue -EnvPath $EnvPath -Key "SUPABASE_FUNCTIONS_URL" -Value $functionsUrl
  Set-EnvValue -EnvPath $EnvPath -Key "SUPABASE_ANON_KEY" -Value $AnonKey
}

function Install-ScheduledTask {
  param(
    [string]$TaskName,
    [string]$PythonPath,
    [string]$EnvPath,
    [string]$WorkingDir
  )

  $args = "-m liftpic_sync.cli --env `"$EnvPath`" run"
  $action = New-ScheduledTaskAction -Execute $PythonPath -Argument $args -WorkingDirectory $WorkingDir
  $trigger = New-ScheduledTaskTrigger -AtStartup
  $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

  if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  }

  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Liftpic Sync starts automatically and watches local photo folders." | Out-Null
  Start-ScheduledTask -TaskName $TaskName
}

Assert-Admin

$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$EnvPath = Join-Path $InstallDir ".env"
$TempRoot = Join-Path $env:TEMP ("liftpic-sync-install-" + [guid]::NewGuid().ToString("N"))
$ZipPath = Join-Path $TempRoot "liftpic-sync.zip"
$ExtractPath = Join-Path $TempRoot "extract"
$VenvDir = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

Write-Host ""
Write-Host "Liftpic Sync Installation"
Write-Host "Zielordner: $InstallDir"
Write-Host ""

New-Item -ItemType Directory -Force -Path $TempRoot, $ExtractPath, $InstallDir | Out-Null

Write-Host "1/6 Lade aktuelle Software von GitHub..."
Invoke-WebRequest -Uri $RepoZipUrl -OutFile $ZipPath
Expand-Archive -Path $ZipPath -DestinationPath $ExtractPath -Force
$SourceDir = Get-ChildItem -Path $ExtractPath -Directory | Select-Object -First 1
if (-not $SourceDir) { throw "Download konnte nicht entpackt werden." }

Write-Host "2/6 Kopiere Dateien nach $InstallDir..."
Copy-Item -Path (Join-Path $SourceDir.FullName "*") -Destination $InstallDir -Recurse -Force

Write-Host "3/6 Pruefe Python..."
$SystemPython = Ensure-Python
if ($SystemPython.EndsWith("py.exe")) {
  & $SystemPython -3 -m venv $VenvDir
} else {
  & $SystemPython -m venv $VenvDir
}

Write-Host "4/6 Installiere Liftpic Sync lokal..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e $InstallDir

Write-Host "5/6 Pruefe Grundeinstellungen..."
Ensure-BaseEnv -EnvPath $EnvPath -BaseUrl $SupabaseUrl -AnonKey $SupabaseAnonKey

if (-not $PairingCode) {
  $PairingCode = Read-Host "Pairing-Code aus Kunden Management eingeben"
}

if (-not $PairingCode) {
  throw "Kein Pairing-Code eingegeben. Installation abgebrochen, ohne Task zu starten."
}

Write-Host "Pruefe Erreichbarkeit von $SupabaseUrl ..."
try {
  Invoke-WebRequest -Uri $SupabaseUrl -Method Head -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop | Out-Null
} catch {
  if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
    Write-Host "  Erreichbar (HTTP $([int]$_.Exception.Response.StatusCode))." -ForegroundColor DarkGray
  } else {
    Write-Host "  WARNUNG: $SupabaseUrl ist von diesem PC aus nicht erreichbar. Pruefe Internetverbindung/Firewall/Proxy." -ForegroundColor Yellow
    Write-Host "  Fehler: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

Write-Host "Kopple diesen PC mit dem Dashboard..."
$PairAttempts = 3
$Paired = $false
for ($attempt = 1; $attempt -le $PairAttempts; $attempt++) {
  & $VenvPython -m liftpic_sync.cli --env $EnvPath pair --code $PairingCode
  if ($LASTEXITCODE -eq 0) {
    $Paired = $true
    break
  }
  if ($attempt -lt $PairAttempts) {
    Write-Host "Pairing-Versuch $attempt von $PairAttempts fehlgeschlagen. Neuer Versuch in 5 Sekunden..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
  }
}

if (-not $Paired) {
  throw "Pairing fehlgeschlagen nach $PairAttempts Versuchen (letzter Exit-Code $LASTEXITCODE). Siehe Fehlermeldung(en) oben. Haeufige Ursachen: Pairing-Code falsch/abgelaufen (im Dashboard neuen Code erzeugen), kein Internetzugang, oder eine Firewall/ein Proxy blockiert $SupabaseUrl. Die Aufgabe LiftpicSync wurde NICHT gestartet."
}

Write-Host "6/6 Richte Autostart ein..."
Install-ScheduledTask -TaskName "LiftpicSync" -PythonPath $VenvPython -EnvPath $EnvPath -WorkingDir $InstallDir

Write-Host ""
Write-Host "Fertig."
Write-Host "Liftpic Sync laeuft jetzt im Hintergrund."
Write-Host "Status pruefen:"
Write-Host "  $VenvPython -m liftpic_sync.cli --env `"$EnvPath`" health"
Write-Host ""
