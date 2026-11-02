param(
 [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f-]{36}$')][string]$InstallationId,
 [Parameter(Mandatory=$true)][ValidatePattern('^https://github.com/john123-05/testsoftware/releases/download/[a-zA-Z0-9._-]+/liftpic-install.zip$')][string]$ArchiveUrl,
 [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ArchiveSha256
)
$ErrorActionPreference='Stop'
$dir='C:\liftpic\liftpic-sync'
if (-not (New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administratorrechte erforderlich.' }
if (-not (Test-Path "$dir\.env")) { throw 'Kein bestehender Agent. Neuinstallation verwenden.' }
$task=Get-ScheduledTask LiftpicSync -ErrorAction SilentlyContinue
$service=Get-Service LiftpicSync -ErrorAction SilentlyContinue
if(-not $task -and -not $service) {throw 'Startmethode unbekannt. Erst Bestand pruefen.'}
$lock=[IO.File]::Open("$dir\.installation.lock",[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
$backup=Join-Path (Split-Path $dir -Parent) ('sicherung-assistent-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
$stopped=$false
try {
 [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
 $tmp=Join-Path $env:TEMP ('liftpictures-update-'+[guid]::NewGuid().ToString('N'));New-Item -ItemType Directory $tmp | Out-Null
 Invoke-WebRequest -UseBasicParsing $ArchiveUrl -OutFile "$tmp\release.zip"
 if((Get-FileHash "$tmp\release.zip" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ArchiveSha256){throw 'Paket-Pruefsumme falsch.'}
 Expand-Archive "$tmp\release.zip" "$tmp\package"
 if(-not(Test-Path "$tmp\package\src\liftpic_sync\assistant_update_config.py")){throw 'Paket unvollstaendig.'}
 if($service){Stop-Service LiftpicSync -Force};if($task){Stop-ScheduledTask LiftpicSync}
 for($i=0;$i -lt 30;$i++){
  $running=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {$_.CommandLine -like '*liftpic_sync*' -and $_.CommandLine.Contains($dir)})
  if(-not $running.Count){break};Start-Sleep -Seconds 1
 }
 if($running.Count){throw 'Alter Agent laeuft noch. Update abgebrochen.'}
 $stopped=$true
 New-Item -ItemType Directory $backup | Out-Null
 Copy-Item "$dir\.env" $backup
 foreach($folder in @('src','state','scripts')){if(Test-Path "$dir\$folder"){Copy-Item "$dir\$folder" $backup -Recurse}}
 if($task){Export-ScheduledTask LiftpicSync | Set-Content "$backup\LiftpicSync.xml" -Encoding Unicode}
 & icacls.exe $backup /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
 if($LASTEXITCODE -ne 0){throw 'Sicherungsrechte fehlen.'}
 Copy-Item "$tmp\package\src" $dir -Recurse -Force;Copy-Item "$tmp\package\scripts" $dir -Recurse -Force
 $python=if(Test-Path "$dir\.venv\Scripts\python.exe"){"$dir\.venv\Scripts\python.exe"}else{(Get-Command python.exe -ErrorAction Stop).Source}
 Push-Location "$dir\src"
 try{& $python -m liftpic_sync.assistant_update_config --installation-id $InstallationId --install-dir $dir;if($LASTEXITCODE -ne 0){throw 'Konfiguration nicht verifiziert.'}}finally{Pop-Location}
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$dir\scripts\assistant_watchdog.ps1"
 if($LASTEXITCODE -ne 0){throw 'Waechter fehlt.'}
 if($service){Start-Service LiftpicSync}else{Start-ScheduledTask LiftpicSync}
 $running=@()
 for($i=0;$i -lt 30 -and -not $running.Count;$i++){Start-Sleep -Seconds 2;$running=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {$_.CommandLine -like '*liftpic_sync*' -and $_.CommandLine.Contains($dir)})}
 $check=Get-Content "$dir\setup-check.json" -Raw | ConvertFrom-Json
 $receipt=@{installation_id=$InstallationId;success=[bool]$running.Count;agent_version='0.4.0';watchdog_verified=[bool](Get-ScheduledTask LiftpicSyncWatchdog -ErrorAction SilentlyContinue);code_matches=[bool]$check.code_matches;source_paths_verified=[bool]$check.source_paths_verified;installed_at=[DateTime]::UtcNow.ToString('o');viewer_sha256=$check.viewer_sha256;issues=@()}
 [IO.File]::WriteAllText("$dir\setup-receipt.json",($receipt|ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
 Push-Location "$dir\src";try{& $python -m liftpic_sync.assistant_receipt --install-dir $dir;if($LASTEXITCODE -ne 0){throw 'Ergebnis konnte nicht gemeldet werden.'}}finally{Pop-Location}
 if(-not $running.Count){throw 'Agent nicht gestartet.'}
 Write-Host "Update abgeschlossen. Sicherung: $backup. Neue Kamera bleibt bis CRM-Freigabe im Testbetrieb."
}catch{
 # Restore prior code, .env and SQLite together after a failed stopped update.
 if($stopped -and (Test-Path "$backup\.env")){
  if($service){Stop-Service LiftpicSync -Force -ErrorAction SilentlyContinue};if($task){Stop-ScheduledTask LiftpicSync -ErrorAction SilentlyContinue}
  Start-Sleep -Seconds 3
  $left=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {$_.CommandLine -like '*liftpic_sync*' -and $_.CommandLine.Contains($dir)})
  if($left.Count){Write-Warning "Automatischer Rueckweg blockiert: Agent laeuft noch. Sicherung: $backup"}else{
   Copy-Item "$backup\.env" $dir -Force
   foreach($folder in @('src','state','scripts')){if(Test-Path "$backup\$folder"){Copy-Item "$backup\$folder" $dir -Recurse -Force}}
   if($service){Start-Service LiftpicSync}else{Start-ScheduledTask LiftpicSync}
   Write-Warning 'Vorheriger Stand wiederhergestellt.'
  }
 }
 throw
}finally{$lock.Dispose()}
