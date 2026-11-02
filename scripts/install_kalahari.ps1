<# Customer-specific wrapper. Same verified archive, one-time pairing and watchdog as the existing installer. #>
param(
 [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{48}$')][string]$Code,
 [Parameter(Mandatory=$true)][ValidatePattern('^https://github.com/john123-05/testsoftware/releases/download/[a-zA-Z0-9._-]+/liftpic-install.zip$')][string]$ArchiveUrl,
 [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ArchiveSha256
)
$ErrorActionPreference='Stop'
# First prove that Bolt's current entry bundle contains the new dedicated route.
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$html=(Invoke-WebRequest -UseBasicParsing 'https://liftpictures-fotos.de/').Content
$entry=[regex]::Match($html,'src="(/assets/index-[A-Za-z0-9_-]+\.js)"').Groups[1].Value
if (-not $entry) { throw 'Veroeffentlichte Claim-Seite nicht pruefbar.' }
$bundle=(Invoke-WebRequest -UseBasicParsing ('https://liftpictures-fotos.de'+$entry)).Content
if (-not $bundle.Contains('kalahari-virginia') -or -not $bundle.Contains('KalahariPage-')) { throw 'Kalahari-Seite zuerst in Bolt veroeffentlichen.' }
$package=Join-Path $env:TEMP ('kalahari-package-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $package | Out-Null
try {
 $archive=Join-Path $package 'release.zip'
 Invoke-WebRequest -UseBasicParsing $ArchiveUrl -OutFile $archive
 if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ArchiveSha256) { throw 'Paket-Pruefsumme falsch.' }
 Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $package 'source')
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'source\scripts\install_assistant.ps1') -Code $Code -ArchiveUrl $ArchiveUrl -ArchiveSha256 $ArchiveSha256
} finally { Remove-Item -LiteralPath $package -Recurse -Force -ErrorAction SilentlyContinue }
if ($LASTEXITCODE -ne 0) { throw 'Installation unvollstaendig. Samuel wird nicht geaendert.' }
$root='C:\liftpic\liftpic-sync'
$task=Get-ScheduledTask -TaskName LiftpicSync
$python=$task.Actions[0].Execute
Push-Location "$root\src"
try {
 & $python -m liftpic_sync.kalahari_setup --install-dir $root
 if ($LASTEXITCODE -ne 0) { throw 'Kalahari-Pruefung fehlgeschlagen. Keine Viewer-Aenderung.' }
 $exe='C:\Liftpic\samuel_neu\PhotoViewerFacebook.exe'
 $viewers=@(Get-CimInstance Win32_Process -Filter "Name='PhotoViewerFacebook.exe'" | Where-Object {$_.ExecutablePath -ieq $exe})
 foreach($viewer in $viewers){
  $process=Get-Process -Id $viewer.ProcessId -ErrorAction Stop
  if (-not $process.CloseMainWindow()) { throw 'Samuel bitte schliessen und die lokale Kalahari-Einrichtung erneut starten.' }
  if (-not $process.WaitForExit(10000)) { throw 'Samuel ist noch offen. Keine Einstellungen geaendert.' }
 }
 try {
  & $python -m liftpic_sync.kalahari_setup --configure-viewer --install-dir $root
  if ($LASTEXITCODE -ne 0) { throw 'Samuel-Konfiguration fehlgeschlagen; Sicherung pruefen.' }
 } finally { if ($viewers.Count -gt 0) { Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) } }
} finally { Pop-Location }
Write-Host 'Kalahari vorbereitet: Agent + Waechter laufen im Testbetrieb, QR-Ziel und Parklogo gesetzt. Lokaler Verkauf aus. Noch kein regulaerer Foto-Upload freigegeben.'
Write-Host 'Jetzt ein neues Foto aufnehmen und dessen QR-Code vergleichen. Onlinezahlungen bleiben ausschliesslich Stripe-TEST, 5.00 USD.'
