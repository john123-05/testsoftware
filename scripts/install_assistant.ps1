<# New installations only. Fixed reviewed release; does not change Settings.xml, prices or legacy programs. #>
param(
 [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{48}$')][string]$Code,
 [Parameter(Mandatory=$true)][ValidatePattern('^https://github.com/john123-05/testsoftware/releases/download/[a-zA-Z0-9._-]+/liftpic-install.zip$')][string]$ArchiveUrl,
 [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ArchiveSha256
)
$ErrorActionPreference='Stop'
$dir='C:\liftpic\liftpic-sync'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Bitte Administrator-PowerShell verwenden.' }
$existingTask=Get-ScheduledTask -TaskName LiftpicSync -ErrorAction SilentlyContinue
$existingService=Get-Service -Name LiftpicSync -ErrorAction SilentlyContinue
if ($existingTask -or $existingService -or ((Test-Path "$dir\.env") -and -not (Test-Path "$dir\.setup-session"))) {
 throw 'Bestehende Installation erkannt. Nicht erneut koppeln. Im CRM den Update-/Ersatzablauf verwenden; lokale Konfiguration bleibt erhalten.'
}
New-Item -ItemType Directory -Path $dir -Force | Out-Null
# Only Administrators and SYSTEM may read persistent device credentials.
& icacls.exe $dir /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Dateirechte konnten nicht eingeschraenkt werden.' }
$lock=Join-Path $dir '.installation.lock'
$lockHandle=$null
try {
 $lockHandle=[IO.File]::Open($lock,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
 $tmp=Join-Path $env:TEMP ('liftpictures-'+[guid]::NewGuid().ToString('N'))
 New-Item -ItemType Directory -Path $tmp | Out-Null
 $zip=Join-Path $tmp 'release.zip'
 Invoke-WebRequest -UseBasicParsing $ArchiveUrl -OutFile $zip
 if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ArchiveSha256) { throw 'Paket-Pruefsumme falsch. Abbruch.' }
 Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $tmp 'package')
 $package=Join-Path $tmp 'package'
 if (-not (Test-Path "$package\src\liftpic_sync\assistant_setup.py")) { throw 'Installationspaket unvollstaendig.' }
 Copy-Item "$package\src" -Destination $dir -Recurse -Force
 Copy-Item "$package\scripts" -Destination $dir -Recurse -Force
 $python=$null
 foreach ($candidate in @(Get-Command python.exe,py.exe -All -ErrorAction SilentlyContinue)) {
  if ($candidate.Source -like '*\WindowsApps\*') { continue }
  $version=& $candidate.Source --version 2>&1
  if ($LASTEXITCODE -eq 0 -and "$version" -match '^Python 3\.(1[1-9]|[2-9][0-9])\.') { $python=$candidate.Source;break }
 }
 if (-not $python) {
  $pythonInstaller=Join-Path $tmp 'python.exe'
  Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $pythonInstaller
  $signature=Get-AuthenticodeSignature -LiteralPath $pythonInstaller
  if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Python Software Foundation*') { throw 'Python-Signatur ungueltig.' }
  $p=Start-Process $pythonInstaller -ArgumentList '/quiet InstallAllUsers=1 Include_test=0 PrependPath=1' -Wait -PassThru
  if ($p.ExitCode -notin @(0,3010)) { throw 'Python-Installation fehlgeschlagen.' }
  $python=Join-Path $env:ProgramFiles 'Python312\python.exe'
  if (-not (Test-Path -LiteralPath $python)) { throw 'Python fehlt nach Installation.' }
 }
 # Resolve py.exe to the real interpreter. No pip, venv or external Python packages needed.
 $python=(& $python -c 'import sys; print(sys.executable)').Trim()
 if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $python)) { throw 'Python nicht startbar.' }
 Push-Location "$dir\src"
 try { & $python -m liftpic_sync.assistant_setup --code $Code --install-dir $dir; if ($LASTEXITCODE -ne 0) { throw 'Kopplung fehlgeschlagen. Keine Aufgabe eingerichtet.' } } finally { Pop-Location }
 $action=New-ScheduledTaskAction -Execute $python -Argument "-m liftpic_sync.cli run --env `"$dir\.env`"" -WorkingDirectory "$dir\src"
 $trigger=New-ScheduledTaskTrigger -AtStartup
 $principal=New-ScheduledTaskPrincipal -UserId SYSTEM -RunLevel Highest
 $settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 20 -RestartInterval (New-TimeSpan -Minutes 1)
 Register-ScheduledTask -TaskName LiftpicSync -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Liftpictures Assistent: Uploader im Testbetrieb' | Out-Null
 # The dedicated watchdog checks the exact install and honors maintenance/pause markers.
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$dir\scripts\assistant_watchdog.ps1"
 if ($LASTEXITCODE -ne 0) { throw 'Waechter konnte nicht eingerichtet werden.' }
 Start-ScheduledTask LiftpicSync
 $running=@()
 for ($i=0;$i -lt 30 -and -not $running.Count;$i++) {
  Start-Sleep -Seconds 2
  $running=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*liftpic_sync.cli run*' -and $_.CommandLine.Contains("$dir\.env") })
 }
 $check=Get-Content "$dir\setup-check.json" -Raw | ConvertFrom-Json
 $watchdog=Get-ScheduledTask -TaskName LiftpicSyncWatchdog -ErrorAction SilentlyContinue
 $receipt=@{success=[bool]$running.Count;agent_version=(Get-Content "$dir\src\liftpic_sync\__init__.py" -Raw | Select-String -Pattern '__version__\s*=\s*"([0-9.]+)"').Matches.Groups[1].Value;
  watchdog_verified=[bool]$watchdog;code_matches=[bool]$check.code_matches;source_paths_verified=[bool]$check.source_paths_verified;
  installed_at=[DateTime]::UtcNow.ToString('o');viewer_sha256=$check.viewer_sha256;issues=@()}
 if (-not $running.Count) {$receipt.issues+= 'agent_not_running'}
 if (-not $watchdog) {$receipt.issues+= 'watchdog_missing'}
 if (-not $check.code_matches) {$receipt.issues+= 'code_mismatch'}
 if (-not $check.source_paths_verified) {$receipt.issues+= 'missing_source'}
 $receiptPath=Join-Path $dir 'setup-receipt.json'
 [IO.File]::WriteAllText($receiptPath,($receipt|ConvertTo-Json -Depth 5),(New-Object Text.UTF8Encoding($false)))
 Push-Location "$dir\src"
 try { & $python -m liftpic_sync.assistant_receipt --install-dir $dir; if ($LASTEXITCODE -ne 0) { throw 'Bericht konnte nicht gesendet werden; lokal gespeichert. CRM noch nicht als fertig markieren.' } } finally { Pop-Location }
 if (-not $receipt.success -or -not $watchdog) { throw 'Installation unvollstaendig. Ergebnis im CRM pruefen.' }
 Remove-Item "$dir\.setup-session" -ErrorAction SilentlyContinue
 Write-Host 'Agent und Waechter eingerichtet. TESTBETRIEB: noch keine echten Uploads. Details und Freigabe im CRM.'
} finally {
 if ($lockHandle) {$lockHandle.Dispose()}
}
