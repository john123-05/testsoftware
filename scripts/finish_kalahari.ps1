<# Continue the already paired Kalahari installation. No installer download, pairing, credential replacement or upload activation. #>
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Bitte Administrator-PowerShell verwenden.' }
$root='C:\liftpic\liftpic-sync'
if (-not (Test-Path "$root\.env") -or -not (Test-Path "$root\setup-receipt.json")) { throw 'Vorbereitete Installation fehlt. Nicht neu koppeln; zuerst Zustand pruefen.' }
$task=Get-ScheduledTask -TaskName LiftpicSync -ErrorAction Stop
$watchdog=Get-ScheduledTask -TaskName LiftpicSyncWatchdog -ErrorAction Stop
if ($task.State -eq 'Disabled' -or $watchdog.State -eq 'Disabled') { throw 'Uploader oder Waechter ist deaktiviert; keine Erfolgsmeldung.' }
$python=$task.Actions[0].Execute
if (-not (Test-Path -LiteralPath $python)) { throw 'Eingerichteter Python-Interpreter fehlt.' }
$lock=$null
try {
 $lock=[IO.File]::Open("$root\.installation.lock",[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 Push-Location "$root\src"
 try {
  # Checks the exact park, machine, camera recipe, source folder and reviewed logo before edits.
  & $python -m liftpic_sync.kalahari_setup --install-dir $root
  if ($LASTEXITCODE -ne 0) { throw 'Kalahari-Vorpruefung fehlgeschlagen. Samuel bleibt unveraendert.' }
  & $python -m liftpic_sync.assistant_receipt --install-dir $root
  if ($LASTEXITCODE -ne 0) { throw 'Installationsbericht noch nicht bestaetigt. Nicht neu installieren; diese Ausgabe zeigen.' }
  $receipt=Get-Content "$root\setup-receipt.json" -Raw | ConvertFrom-Json
  if (-not $receipt.success -or -not $receipt.watchdog_verified -or -not $receipt.code_matches -or -not $receipt.source_paths_verified) { throw 'Lokale Installationspruefung unvollstaendig. Keine Viewer-Aenderung.' }
  $running=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*liftpic_sync.cli run*' -and $_.CommandLine.Contains("$root\.env") })
  if (-not $running.Count) { throw 'Uploader laeuft momentan nicht. Keine Erfolgsmeldung; zuerst Prozess pruefen.' }
  $exe='C:\Liftpic\samuel_neu\PhotoViewerFacebook.exe'
  $viewers=@(Get-CimInstance Win32_Process -Filter "Name='PhotoViewerFacebook.exe'" | Where-Object {$_.ExecutablePath -ieq $exe})
  foreach($viewer in $viewers){
   $process=Get-Process -Id $viewer.ProcessId -ErrorAction SilentlyContinue
   if (-not $process) { continue }
   if (-not $process.CloseMainWindow()) { throw 'Samuel bitte geordnet schliessen und diesen Fortsetzungsbefehl erneut ausfuehren.' }
   if (-not $process.WaitForExit(10000)) { throw 'Samuel ist noch offen. Keine Einstellungen geaendert.' }
  }
  try {
   & $python -m liftpic_sync.kalahari_setup --configure-viewer --install-dir $root
   if ($LASTEXITCODE -ne 0) { throw 'Samuel-Konfiguration fehlgeschlagen; Sicherung pruefen.' }
  } finally {
   $open=@(Get-CimInstance Win32_Process -Filter "Name='PhotoViewerFacebook.exe'" | Where-Object {$_.ExecutablePath -ieq $exe})
   if (-not $open.Count -and (Test-Path -LiteralPath $exe)) { Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) }
  }
  Remove-Item "$root\.setup-session" -ErrorAction SilentlyContinue
 } finally { Pop-Location }
 Write-Host 'Kalahari-Einrichtung abgeschlossen: Bericht bestaetigt, Uploader + Waechter vorhanden, QR-Ziel und Parklogo gesetzt.'
 Write-Host 'Pruefmodus bleibt aktiv. Jetzt ein neues eigenes Testfoto aufnehmen und den Samuel-QR-Code vergleichen. Stripe bleibt ausschliesslich TEST.'
} finally { if ($lock) { $lock.Dispose() } }
