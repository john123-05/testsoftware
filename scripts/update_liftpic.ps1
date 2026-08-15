<#
.SYNOPSIS
  Einen BESTEHENDEN Automaten aktualisieren, ohne ihn neu einzurichten.

.DESCRIPTION
  Der Bootstrap-Installer ist ein Einrichtungswerkzeug, kein Update-Werkzeug:

    * Er verlangt IMMER einen Pairing-Code und koppelt bedingungslos neu.
      Das Koppeln ueberschreibt 16 Schluessel in der .env mit Serverwerten und
      harten Vorgabepfaden - nicht der Installer verstellt die Pfade, das
      Koppeln tut es.
    * Er haelt den laufenden Agenten NICHT an, bevor er Dateien kopiert und
      `pip install` ausfuehrt. Der alte Agent laeuft dabei mit teilweise
      ersetztem Code weiter.
    * Er sichert nichts.

  Dieses Skript macht das Gegenteil: anhalten, sichern, aktualisieren,
  pruefen - und nur koppeln, wenn wirklich kein Token da ist.

.PARAMETER Tag
  Der Git-Tag, aus dem installiert wird. Ohne Angabe wird `main` genommen.
  Fuer einen Rueckweg den Tag des vorherigen Standes angeben.

.EXAMPLE
  .\update_liftpic.ps1 -Tag v0.2.0-haertung
  .\update_liftpic.ps1 -Tag v0.1.0-imst-stand   # zurueck auf den alten Stand
#>
param(
  [string]$InstallDir = "C:\liftpic\liftpic-sync",
  [string]$Tag = "",
  [string]$Repo = "https://github.com/john123-05/testsoftware",
  [switch]$OhneSicherung
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Bitte als Administrator ausfuehren."
}

$EnvPath   = Join-Path $InstallDir ".env"
$StateDir  = Join-Path $InstallDir "state"
$VenvPy    = Join-Path $InstallDir ".venv\Scripts\python.exe"
$Aufgabe   = "LiftpicSync"

if (-not (Test-Path $EnvPath)) {
  throw "Keine .env unter $EnvPath - das ist keine bestehende Installation. Fuer eine Neuinstallation den Bootstrap-Installer nehmen."
}

$quelle = if ($Tag) { "$Repo/archive/refs/tags/$Tag.zip" } else { "$Repo/archive/refs/heads/main.zip" }
Write-Host ""
Write-Host "Aktualisierung von $InstallDir"
Write-Host "Quelle: $quelle"
Write-Host ""


# ------------------------------------------------------------ 1/6 Anhalten
Write-Host "1/6 Agenten anhalten..."

$aufgabeVorhanden = Get-ScheduledTask -TaskName $Aufgabe -ErrorAction SilentlyContinue
$dienstVorhanden  = Get-Service -Name $Aufgabe -ErrorAction SilentlyContinue

if ($dienstVorhanden -and $aufgabeVorhanden) {
  Write-Warning "Es gibt einen Dienst UND eine Aufgabe namens $Aufgabe - das sind zwei Agenten."
  Write-Warning "Beide werden angehalten; nach dem Update bitte install_windows_service.ps1 laufen lassen."
}
if ($dienstVorhanden)  { Stop-Service -Name $Aufgabe -Force -ErrorAction SilentlyContinue }
if ($aufgabeVorhanden) { Stop-ScheduledTask -TaskName $Aufgabe -ErrorAction SilentlyContinue }

# Warten, bis die Prozesse wirklich weg sind. Der venv-Starter hat den echten
# Interpreter als Kindprozess; Stop-ScheduledTask kehrt sofort zurueck.
$weg = $false
for ($i = 0; $i -lt 40; $i++) {
  $rest = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*liftpic_sync*" })
  if (-not $rest) { $weg = $true; break }
  if ($i -eq 10) {
    Write-Host "  reagiert nicht, beende die Prozesse direkt..."
    foreach ($p in $rest) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
  }
  Start-Sleep -Milliseconds 500
}
if (-not $weg) { throw "Der alte Agent laeuft noch. Abbruch - ein Update bei laufendem Agenten mischt zwei Codestaende." }
Write-Host "  angehalten."


# ------------------------------------------------------------ 2/6 Sichern
if ($OhneSicherung) {
  Write-Warning "2/6 Sicherung uebersprungen (-OhneSicherung)."
  $sicherung = $null
} else {
  $stempel   = Get-Date -Format "yyyyMMdd-HHmmss"
  $sicherung = Join-Path (Split-Path $InstallDir -Parent) "sicherung-liftpic-sync-$stempel"
  Write-Host "2/6 Sichere nach $sicherung ..."
  New-Item -ItemType Directory -Force -Path $sicherung | Out-Null

  Copy-Item $EnvPath (Join-Path $sicherung ".env") -Force
  # Die Zustandsdatenbank NUR zusammen mit -wal und -shm - ohne die beiden ist
  # sie unvollstaendig (die -wal war hier schon 4 MB gross).
  if (Test-Path $StateDir) {
    Copy-Item $StateDir (Join-Path $sicherung "state") -Recurse -Force
  }
  # Die Aufgabe wird beim Update neu angelegt; ohne Export ist jede lokale
  # Anpassung daran verloren.
  if ($aufgabeVorhanden) {
    Export-ScheduledTask -TaskName $Aufgabe |
      Out-File (Join-Path $sicherung "LiftpicSync.xml") -Encoding utf8
  }
  # Der Programmstand selbst, damit ein Rueckweg auch ohne Netz geht.
  Copy-Item (Join-Path $InstallDir "src") (Join-Path $sicherung "src") -Recurse -Force -ErrorAction SilentlyContinue

  Write-Host "  gesichert."
}


# ------------------------------------------------------------ 3/6 Herunterladen
Write-Host "3/6 Lade $quelle ..."
$temp = Join-Path $env:TEMP "liftpic-update-$(Get-Random)"
New-Item -ItemType Directory -Force -Path $temp | Out-Null
$zip = Join-Path $temp "quelle.zip"
Invoke-WebRequest -Uri $quelle -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath $temp -Force
$entpackt = Get-ChildItem -Path $temp -Directory | Select-Object -First 1
if (-not $entpackt) { throw "Das Archiv liess sich nicht entpacken." }


# ------------------------------------------------------------ 4/6 Kopieren
Write-Host "4/6 Kopiere den neuen Stand..."
# .env, state, logs und backups liegen nicht im Archiv und ueberleben deshalb.
Copy-Item -Path (Join-Path $entpackt.FullName "*") -Destination $InstallDir -Recurse -Force

if (-not (Test-Path $VenvPy)) { throw "Kein venv unter $VenvPy - bitte den Bootstrap-Installer nehmen." }
& $VenvPy -m pip install -e $InstallDir --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install fehlgeschlagen - der alte Stand liegt in $sicherung" }


# ------------------------------------------------------------ 5/6 Kopplung
Write-Host "5/6 Pruefe die Kopplung..."
$envText = Get-Content $EnvPath -Encoding UTF8
$token = ($envText | Where-Object { $_ -match "^\s*DEVICE_TOKEN\s*=\s*(.+)$" } |
          ForEach-Object { $Matches[1].Trim() } | Select-Object -First 1)

if ($token) {
  Write-Host "  Geraetetoken vorhanden - es wird NICHT neu gekoppelt."
  Write-Host "  (Das Koppeln wuerde 16 Schluessel mit Serverwerten ueberschreiben.)"
} else {
  Write-Warning "  Kein Geraetetoken in der .env. Dieser Automat muss gekoppelt werden:"
  Write-Warning "  $VenvPy -m liftpic_sync.cli pair --code <CODE> --env $EnvPath"
}


# ------------------------------------------------------------ 6/6 Bericht
Write-Host "6/6 Lage nach dem Update:"
Write-Host ""
& $VenvPy -m liftpic_sync.cli preflight --env $EnvPath
Write-Host ""

if ($dienstVorhanden)  { Start-Service -Name $Aufgabe }
elseif ($aufgabeVorhanden) { Start-ScheduledTask -TaskName $Aufgabe }
else { Write-Warning "Weder Dienst noch Aufgabe gefunden - der Agent muss von Hand gestartet werden." }

Start-Sleep -Seconds 6
$laufend = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -like "*liftpic_sync*" })
Write-Host ""
Write-Host "Fertig. Laufende Agenten-Prozesse: $($laufend.Count) (Starter + Interpreter = ein Agent)"
if ($sicherung) {
  Write-Host "Rueckweg:  .\rollback_lokal.ps1 -Sicherung `"$sicherung`""
}
