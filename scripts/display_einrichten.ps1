<#
.SYNOPSIS
  Liftpictures Display installieren: Presentation (2. Monitor) und Station
  (Systemzustand) als eigenes Programm statt im Browser.

.DESCRIPTION
  Laedt LiftpicturesDisplay.zip aus dem GitHub-Release der Agent-Version,
  entpackt nach C:\liftpic\display und legt die Verknuepfungen an:
    Autostart  "Liftpictures Screen"   -> LiftpicturesDisplay.exe --presentation
    Autostart  "Liftpictures Station"  -> LiftpicturesDisplay.exe --station
    Desktop + Startmenue (Liftpictures): "Liftpictures Presentation", "Liftpictures Station"
  Alte Edge-Fenster (Kiosk/App) werden geschlossen, beide Ansichten gestartet.
  Die alte Autostart-Einstellung des Gaeste-Bildschirms wird einmal gesichert.
  Zurueck zur Online-Seite: scripts\presentation_einrichten.ps1 -Online

  Als angemeldeter Benutzer bzw. in dessen Administrator-PowerShell ausfuehren.
  Kamera-Software und Verkaufsprogramm werden nicht angefasst.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\liftpic\liftpic-sync\scripts\display_einrichten.ps1 -Tag v0.5.0
#>
param(
  [string]$Tag = "",
  [string]$Dir = "C:\liftpic\display",
  [string]$Repo = "https://github.com/john123-05/testsoftware",
  [switch]$OhnePresentation
)
$ErrorActionPreference = "Stop"

if (-not $Tag) {
  $init = "C:\liftpic\liftpic-sync\src\liftpic_sync\__init__.py"
  $m = if (Test-Path $init) { Select-String -Path $init -Pattern '__version__\s*=\s*"([^"]+)"' } else { $null }
  if (-not $m) { throw "Agent-Version nicht gefunden - bitte -Tag v0.5.0 angeben." }
  $Tag = "v" + $m.Matches[0].Groups[1].Value
}

# 1) Herunterladen und entpacken
$url = "$Repo/releases/download/$Tag/LiftpicturesDisplay.zip"
$zip = Join-Path $env:TEMP "LiftpicturesDisplay-$Tag.zip"
Write-Host "1/4 Lade $url ..."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip

Write-Host "2/4 Installiere nach $Dir ..."
Get-Process -Name LiftpicturesDisplay -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
Expand-Archive -Path $zip -DestinationPath $Dir -Force
Get-ChildItem $Dir -Recurse -File | Unblock-File
$exe = Join-Path $Dir "LiftpicturesDisplay.exe"
if (-not (Test-Path $exe)) { throw "LiftpicturesDisplay.exe fehlt in $Dir." }

# 2) Verknuepfungen
Write-Host "3/4 Verknuepfungen ..."
$shell = New-Object -ComObject WScript.Shell
function Lnk([string]$Pfad, [string]$Argumente, [string]$Text) {
  $l = $shell.CreateShortcut($Pfad)
  $l.TargetPath = $exe
  $l.Arguments = $Argumente
  $l.WorkingDirectory = $Dir
  $l.IconLocation = "$exe,0"
  $l.Description = $Text
  $l.Save()
  Write-Host "   $Pfad"
}
$startup = [Environment]::GetFolderPath("Startup")
$desktop = [Environment]::GetFolderPath("Desktop")
$startmenue = Join-Path ([Environment]::GetFolderPath("Programs")) "Liftpictures"
New-Item -ItemType Directory -Force -Path $startmenue | Out-Null

if (-not $OhnePresentation) {
  $screenLnk = Join-Path $startup "Liftpictures Screen.lnk"
  $sicherung = Join-Path $env:LOCALAPPDATA "liftpictures-screen-shortcut-backup.txt"
  if ((Test-Path $screenLnk) -and -not (Test-Path $sicherung)) {
    $alt = $shell.CreateShortcut($screenLnk)
    "$($alt.TargetPath) $($alt.Arguments)" | Out-File $sicherung -Encoding utf8
  }
  Lnk $screenLnk "--presentation" "Liftpictures Presentation (second monitor)"
  Lnk (Join-Path $desktop "Liftpictures Presentation.lnk") "--presentation" "Liftpictures Presentation (second monitor)"
  Lnk (Join-Path $startmenue "Liftpictures Presentation.lnk") "--presentation" "Liftpictures Presentation (second monitor)"
}
Lnk (Join-Path $startup "Liftpictures Station.lnk") "--station" "Liftpictures Station - system status of this photo PC"
Lnk (Join-Path $desktop "Liftpictures Station.lnk") "--station" "Liftpictures Station - system status of this photo PC"
Lnk (Join-Path $startmenue "Liftpictures Station.lnk") "--station" "Liftpictures Station - system status of this photo PC"

# 3) Alte Browser-Fenster schliessen, Programm starten
Write-Host "4/4 Starte ..."
Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*station-profile*" -or (-not $OhnePresentation -and $_.CommandLine -like "*screen-profile*") } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
if (-not $OhnePresentation) { Start-Process -FilePath $exe -ArgumentList "--presentation" -WorkingDirectory $Dir }
Start-Process -FilePath $exe -ArgumentList "--station" -WorkingDirectory $Dir

Write-Host ""
Write-Host "Fertig. Liftpictures Display $Tag laeuft."
Write-Host "An die Taskleiste: Start-Taste, 'Liftpictures Station' tippen, Rechtsklick > 'An Taskleiste anheften'."
Write-Host "Zurueck zur Online-Seite auf Monitor 2: scripts\presentation_einrichten.ps1 -Online"
