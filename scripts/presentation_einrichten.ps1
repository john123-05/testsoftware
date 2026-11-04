<#
.SYNOPSIS
  Liftpictures Presentation auf den zweiten Monitor legen (ersetzt die
  Online-Gaeste-Seite) - oder mit -Online wieder zurueck.

.DESCRIPTION
  Die Presentation ist der Nachbau der Praesentation des Verkaufsprogramms
  (blaues Raster, Bildnummer + Uhrzeit, Laufband), aber mit QR-Codes, die den
  echten Kauf-Link enthalten. Der Agent schreibt sie nach
  C:\liftpic\presentation, sobald sie im Dashboard fuer diesen PC
  freigeschaltet ist (presentation_enabled).

  Das Skript wartet bis zu 2 Minuten auf einen frischen Stand des Agenten,
  stellt die Autostart-Verknuepfung "Liftpictures Screen" auf die lokale Seite
  um (die alte Einstellung wird daneben gesichert), schliesst das bisherige
  Fenster und oeffnet die Presentation im Vollbild auf dem zweiten Monitor.
  Mehrfach ausfuehren schadet nicht. Kamera-Software und Verkaufsprogramm
  werden nicht angefasst.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\liftpic\liftpic-sync\scripts\presentation_einrichten.ps1
  powershell -ExecutionPolicy Bypass -File C:\liftpic\liftpic-sync\scripts\presentation_einrichten.ps1 -Online
#>
param(
  [string]$Dir = "C:\liftpic\presentation",
  [string]$OnlineUrl = "https://liftpictures-fotos.de/kalahari-virginia/screen",
  [switch]$Online
)
$ErrorActionPreference = "Stop"

$edge = @(
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
  "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { throw "Microsoft Edge wurde nicht gefunden." }

# Zweiter Monitor: der erste, der nicht der Hauptbildschirm ist.
Add-Type -AssemblyName System.Windows.Forms
$zweiter = [System.Windows.Forms.Screen]::AllScreens | Where-Object { -not $_.Primary } | Select-Object -First 1
if (-not $zweiter) { throw "Kein zweiter Monitor gefunden." }
$x = $zweiter.Bounds.X; $y = $zweiter.Bounds.Y

if ($Online) {
  $ziel = $OnlineUrl
} else {
  $seite = Join-Path $Dir "index.html"
  $stand = Join-Path $Dir "photos.js"
  $start = Get-Date
  Write-Host "Warte auf den Agenten (bis zu 2 Minuten)..."
  for ($i = 0; $i -lt 24; $i++) {
    if ((Test-Path $stand) -and (Get-Item $stand).LastWriteTime -gt $start.AddSeconds(-30)) { break }
    Start-Sleep -Seconds 5
  }
  if (-not (Test-Path $seite)) {
    throw "Keine Presentation unter $seite. Ist sie im Dashboard fuer diesen PC freigeschaltet und laeuft Liftpic Sync ab 0.4.8?"
  }
  if ((Get-Content $stand -Raw) -match '"licensed":false') {
    Write-Warning "Die Presentation ist fuer diesen PC (noch) nicht freigeschaltet - sie zeigt einen Hinweis statt Fotos."
  }
  $ziel = "file:///" + ($seite -replace "\\", "/")
}

$profil = "C:\liftpic\screen-profile"
$argumente = "--kiosk $ziel --edge-kiosk-type=fullscreen --window-position=$x,$y --user-data-dir=`"$profil`" --no-first-run --no-default-browser-check"

$shell = New-Object -ComObject WScript.Shell
$pfad = Join-Path ([Environment]::GetFolderPath("Startup")) "Liftpictures Screen.lnk"
if (Test-Path $pfad) {
  $alt = $shell.CreateShortcut($pfad)
  $sicherung = Join-Path $env:LOCALAPPDATA "liftpictures-screen-shortcut-backup.txt"
  if (-not (Test-Path $sicherung)) { "$($alt.TargetPath) $($alt.Arguments)" | Out-File $sicherung -Encoding utf8 }
}
$lnk = $shell.CreateShortcut($pfad)
$lnk.TargetPath = $edge
$lnk.Arguments = $argumente
$lnk.Description = "Liftpictures guest screen (second monitor)"
$lnk.Save()
Write-Host "Autostart: $pfad -> $ziel"

# Bisheriges Fenster auf dem zweiten Monitor schliessen (Edge mit diesem Profil
# oder das Programm Liftpictures Display mit --presentation).
Get-CimInstance Win32_Process -Filter "Name='msedge.exe' or Name='LiftpicturesDisplay.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*screen-profile*" -or $_.CommandLine -like "*--presentation*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Start-Process -FilePath $edge -ArgumentList $argumente
Write-Host "Zweiter Monitor zeigt jetzt: $ziel"
