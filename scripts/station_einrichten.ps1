<#
.SYNOPSIS
  Liftpictures Station einrichten: Verknuepfung im Autostart und auf dem
  Desktop, dann die Seite im Vollbild auf dem Hauptmonitor oeffnen.

.DESCRIPTION
  Die Station ist eine lokale Statusseite (C:\liftpic\station\index.html), die
  der Agent ab 0.4.3 bei jedem Herzschlag schreibt. Sie laeuft ohne Internet.
  Dieses Skript wartet bis zu 3 Minuten auf die Seite, legt die beiden
  Verknuepfungen "Liftpictures Station" an und oeffnet sie. Ein schon offenes
  Station-Fenster wird vorher geschlossen. Mehrfach ausfuehren schadet nicht.

  Als der am Automaten angemeldete Benutzer ausfuehren (AnyDesk-PowerShell
  reicht, Administrator ist nicht noetig). Die Kamera-Software und der
  Gaeste-Bildschirm werden NICHT angefasst.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\liftpic\liftpic-sync\scripts\station_einrichten.ps1
#>
param(
  [string]$Dir = "C:\liftpic\station",
  [int]$X = 0,
  [int]$Y = 0
)
$ErrorActionPreference = "Stop"

$seite = Join-Path $Dir "index.html"
for ($i = 0; $i -lt 36 -and -not (Test-Path $seite); $i++) {
  if ($i -eq 0) { Write-Host "Warte auf die Station-Seite vom Agenten..." }
  Start-Sleep -Seconds 5
}
if (-not (Test-Path $seite)) {
  throw "Keine Seite unter $seite. Laeuft Liftpic Sync ab Version 0.4.3? (Aufgabe LiftpicSync pruefen)"
}

$edge = @(
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
  "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { throw "Microsoft Edge wurde nicht gefunden." }

$profil = "$Dir-profile"
$url = "file:///" + ($seite -replace "\\", "/")
$argumente = "--app=$url --start-fullscreen --window-position=$X,$Y --user-data-dir=`"$profil`" --no-first-run --no-default-browser-check"

$shell = New-Object -ComObject WScript.Shell
foreach ($ordner in @([Environment]::GetFolderPath("Startup"), [Environment]::GetFolderPath("Desktop"))) {
  $lnk = $shell.CreateShortcut((Join-Path $ordner "Liftpictures Station.lnk"))
  $lnk.TargetPath = $edge
  $lnk.Arguments = $argumente
  $lnk.WorkingDirectory = $Dir
  $lnk.Description = "Liftpictures Station - system status of this photo PC"
  $lnk.IconLocation = "$edge,0"
  $lnk.Save()
  Write-Host "Verknuepfung: $($lnk.FullName)"
}

# Ein altes Station-Fenster schliessen (nur das mit dem Station-Profil).
Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*$profil*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

Start-Process -FilePath $edge -ArgumentList $argumente
Write-Host "Liftpictures Station ist offen. Schliessen: Knopf 'Hide screen' oben rechts oder Esc."
