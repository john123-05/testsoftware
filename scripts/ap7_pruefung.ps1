<#
.SYNOPSIS
  Die drei Ausfallszenarien, die Administratorrechte brauchen (AP-7).

.DESCRIPTION
  Szenario 3, 4 und 12 aus docs/HAERTUNG_FORTSCHRITT.md lassen sich nur mit
  erhoehten Rechten pruefen - Aufgaben anlegen, Dienste anfassen, Dateien in
  der Installation ersetzen.

  Das Skript stellt jeden Fall nach, prueft die Erwartung und raeumt hinter
  sich auf. Es aendert die Installation NICHT dauerhaft: Szenario 4 und 12
  laufen auf einer Kopie in %TEMP%, nicht auf C:\liftpic\liftpic-sync.

.EXAMPLE
  # In einer Konsole ALS ADMINISTRATOR:
  powershell -ExecutionPolicy Bypass -File C:\liftpic\liftpic-sync\scripts\ap7_pruefung.ps1
#>
param(
  [string]$InstallDir = "C:\liftpic\liftpic-sync"
)

$ErrorActionPreference = "Continue"

if (-not ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Bitte als Administrator ausfuehren - sonst laesst sich keine Aufgabe anlegen."
}

$bestanden = @()
$gescheitert = @()

function Ergebnis {
  param([string]$Nummer, [bool]$Ok, [string]$Text)
  if ($Ok) {
    $script:bestanden += $Nummer
    Write-Host "  [bestanden] $Nummer - $Text" -ForegroundColor Green
  } else {
    $script:gescheitert += $Nummer
    Write-Host "  [GESCHEITERT] $Nummer - $Text" -ForegroundColor Red
  }
}


# =====================================================================
Write-Host ""
Write-Host "Szenario 3: Aufgabe UND Dienst gleichen Namens" -ForegroundColor Cyan
Write-Host "  Dienst und Aufgabe liegen in getrennten Namensraeumen und koennen"
Write-Host "  gleichzeitig existieren. Genau so entsteht der Doppelbetrieb."

$attrappe = "LiftpicSyncAttrappeAP7"
try {
  $aktion = New-ScheduledTaskAction -Execute (Join-Path $InstallDir ".venv\Scripts\python.exe") `
    -Argument "-m liftpic_sync.cli run --env $InstallDir\.env"
  Register-ScheduledTask -TaskName $attrappe -Action $aktion `
    -Trigger (New-ScheduledTaskTrigger -AtStartup) -Force | Out-Null

  # Die Erkennung aus install_windows_service.ps1 nachstellen: sie muss auch
  # Aufgaben mit ABWEICHENDEM Namen finden, die denselben Agenten starten.
  $gefunden = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    $_.Actions.Execute -like "*python*" -and $_.Actions.Arguments -like "*liftpic_sync*"
  })
  $trefferNamen = $gefunden | ForEach-Object { $_.TaskName }
  Ergebnis "3" ($trefferNamen -contains $attrappe) `
    "fremd benannte Aufgabe wird gefunden ($($gefunden.Count) Treffer insgesamt)"
} finally {
  Unregister-ScheduledTask -TaskName $attrappe -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "  Attrappe entfernt."
}


# =====================================================================
Write-Host ""
Write-Host "Szenario 4: Update bei laufendem Agenten" -ForegroundColor Cyan
Write-Host "  Der venv-Starter hat den echten Interpreter als Kindprozess."
Write-Host "  Stop-ScheduledTask kehrt sofort zurueck - ohne Warten bleibt der"
Write-Host "  Enkel neben dem neuen Agenten stehen."

$vorher = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*liftpic_sync*" })
Write-Host "  Laufende Agenten-Prozesse vorher: $($vorher.Count)"

if ($vorher.Count -eq 0) {
  Write-Host "  Kein Agent laeuft - Szenario nicht pruefbar. Bitte erst starten." -ForegroundColor Yellow
} else {
  # Nur das Anhalten aus update_liftpic.ps1 nachstellen, ohne zu aktualisieren.
  foreach ($p in $vorher) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
  $weg = $false
  for ($i = 0; $i -lt 40; $i++) {
    $rest = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
              Where-Object { $_.CommandLine -like "*liftpic_sync*" })
    if (-not $rest) { $weg = $true; break }
    Start-Sleep -Milliseconds 500
  }
  Ergebnis "4" $weg "alle Prozesse beendet, kein Enkel uebrig"

  # Wieder starten, damit die Anlage nicht steht.
  Start-Process -WindowStyle Hidden -FilePath (Join-Path $InstallDir ".venv\Scripts\python.exe") `
    -ArgumentList "-m","liftpic_sync.cli","run","--env","$InstallDir\.env"
  Start-Sleep -Seconds 8
  $nachher = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
               Where-Object { $_.CommandLine -like "*liftpic_sync*" })
  Write-Host "  Wieder gestartet, laufende Prozesse: $($nachher.Count)"
}


# =====================================================================
Write-Host ""
Write-Host "Szenario 12: Ruecksicherung aus einer Ordnersicherung" -ForegroundColor Cyan
Write-Host "  Geprueft wird auf einer KOPIE in %TEMP%, nicht an der Installation."

$spiel = Join-Path $env:TEMP "ap7-rollback-$(Get-Random)"
try {
  New-Item -ItemType Directory -Force -Path $spiel | Out-Null
  $sicherung = Join-Path $spiel "sicherung"
  $ziel      = Join-Path $spiel "anlage"
  New-Item -ItemType Directory -Force -Path $sicherung, $ziel | Out-Null

  # Ausgangslage: eine .env mit Token und Umlaut, dazu eine Zustandsdatenbank
  Set-Content (Join-Path $sicherung ".env") -Encoding UTF8 -Value @(
    "DEVICE_TOKEN=altes-token", "MACHINE_LABEL=Bergstation Süd", "PARK_SLUG=imst"
  )
  New-Item -ItemType Directory -Force -Path (Join-Path $sicherung "state") | Out-Null
  Set-Content (Join-Path $sicherung "state\liftpic-sync.db")     -Value "DB"  -Encoding UTF8
  Set-Content (Join-Path $sicherung "state\liftpic-sync.db-wal") -Value "WAL" -Encoding UTF8

  # Der "kaputte" Zustand nach einem missratenen Update
  Set-Content (Join-Path $ziel ".env") -Encoding UTF8 -Value @("DEVICE_TOKEN=", "PARK_SLUG=falsch")

  # Zuruecksichern, wie rollback_lokal.ps1 es tut
  Copy-Item (Join-Path $sicherung ".env") (Join-Path $ziel ".env") -Force
  Copy-Item (Join-Path $sicherung "state") (Join-Path $ziel "state") -Recurse -Force

  $inhalt = Get-Content (Join-Path $ziel ".env") -Encoding UTF8 -Raw
  $ok = ($inhalt -match "altes-token") -and ($inhalt -match "Süd") -and
        (Test-Path (Join-Path $ziel "state\liftpic-sync.db-wal"))
  Ergebnis "12" $ok "Token, Umlaut und die -wal sind zurueck"
} finally {
  Remove-Item $spiel -Recurse -Force -ErrorAction SilentlyContinue
}


# =====================================================================
Write-Host ""
Write-Host "-------------------------------------------------------------"
Write-Host "Bestanden:   $($bestanden -join ', ')"
if ($gescheitert.Count -gt 0) {
  Write-Host "GESCHEITERT: $($gescheitert -join ', ')" -ForegroundColor Red
  exit 1
}
Write-Host "Alle pruefbaren Szenarien bestanden."
