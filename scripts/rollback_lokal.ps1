<#
.SYNOPSIS
  Einen Automaten aus einer Ordnersicherung zurueckholen - ohne Git.

.DESCRIPTION
  Das mitgelieferte `rollback.ps1` macht `git checkout <Tag>` und setzt damit
  ein Git-Repo voraus. Auf einem installierten Automaten gibt es keines, dort
  liegen nur entpackte Dateien - es ist auf einer Anlage schlicht unbrauchbar.

  Dieses Skript spielt zurueck, was `update_liftpic.ps1` gesichert hat:
  die .env, die Zustandsdatenbank samt -wal und -shm, den Programmstand und
  die exportierte Aufgabe.

  Die Kopplung bleibt dabei erhalten: sie haengt am Datensatz auf dem Server
  und am Gerätetoken in der .env, nicht am Programmstand.

.EXAMPLE
  .\rollback_lokal.ps1 -Sicherung C:\liftpic\sicherung-liftpic-sync-20260815-213000
#>
param(
  [Parameter(Mandatory = $true)][string]$Sicherung,
  [string]$InstallDir = "C:\liftpic\liftpic-sync"
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Bitte als Administrator ausfuehren."
}
if (-not (Test-Path $Sicherung)) { throw "Sicherung nicht gefunden: $Sicherung" }

$Aufgabe = "LiftpicSync"
$EnvPath = Join-Path $InstallDir ".env"

Write-Host ""
Write-Host "Ruecksicherung aus $Sicherung"
Write-Host "Ziel: $InstallDir"
Write-Host ""

# ----------------------------------------------------------------- Anhalten
Write-Host "1/4 Agenten anhalten..."
$dienst  = Get-Service -Name $Aufgabe -ErrorAction SilentlyContinue
$aufgabe = Get-ScheduledTask -TaskName $Aufgabe -ErrorAction SilentlyContinue
if ($dienst)  { Stop-Service -Name $Aufgabe -Force -ErrorAction SilentlyContinue }
if ($aufgabe) { Stop-ScheduledTask -TaskName $Aufgabe -ErrorAction SilentlyContinue }

$weg = $false
for ($i = 0; $i -lt 40; $i++) {
  $rest = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*liftpic_sync*" })
  if (-not $rest) { $weg = $true; break }
  if ($i -eq 10) { foreach ($p in $rest) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } }
  Start-Sleep -Milliseconds 500
}
if (-not $weg) { throw "Der Agent laeuft noch - keine Ruecksicherung, solange er schreibt." }

# ------------------------------------------------------------ Zurueckspielen
Write-Host "2/4 Spiele zurueck..."

$gesichertesEnv = Join-Path $Sicherung ".env"
if (Test-Path $gesichertesEnv) {
  Copy-Item $gesichertesEnv $EnvPath -Force
  Write-Host "  .env"
} else {
  Write-Warning "  keine .env in der Sicherung - die vorhandene bleibt stehen"
}

$gesicherterState = Join-Path $Sicherung "state"
if (Test-Path $gesicherterState) {
  $ziel = Join-Path $InstallDir "state"
  if (Test-Path $ziel) { Remove-Item $ziel -Recurse -Force }
  Copy-Item $gesicherterState $ziel -Recurse -Force
  Write-Host "  state (inkl. -wal und -shm)"
}

$gesicherterSrc = Join-Path $Sicherung "src"
if (Test-Path $gesicherterSrc) {
  Copy-Item (Join-Path $gesicherterSrc "*") (Join-Path $InstallDir "src") -Recurse -Force
  Write-Host "  Programmstand"
  $venvPy = Join-Path $InstallDir ".venv\Scripts\python.exe"
  if (Test-Path $venvPy) { & $venvPy -m pip install -e $InstallDir --quiet }
}

# ---------------------------------------------------------------- Aufgabe
Write-Host "3/4 Aufgabe wiederherstellen..."
$xml = Join-Path $Sicherung "LiftpicSync.xml"
if ((Test-Path $xml) -and -not $aufgabe) {
  Register-ScheduledTask -TaskName $Aufgabe -Xml (Get-Content $xml -Raw) -Force | Out-Null
  Write-Host "  aus der Sicherung angelegt"
} elseif ($aufgabe) {
  Write-Host "  vorhanden, bleibt unveraendert"
} else {
  Write-Warning "  keine Aufgabe in der Sicherung und keine vorhandene"
}

# ----------------------------------------------------------------- Starten
Write-Host "4/4 Starten und pruefen..."
if ($dienst)      { Start-Service -Name $Aufgabe }
elseif (Get-ScheduledTask -TaskName $Aufgabe -ErrorAction SilentlyContinue) { Start-ScheduledTask -TaskName $Aufgabe }
else { Write-Warning "  Weder Dienst noch Aufgabe - der Agent muss von Hand gestartet werden." }

Start-Sleep -Seconds 6
$laufend = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -like "*liftpic_sync*" })
Write-Host ""
Write-Host "Zurueckgespielt. Laufende Agenten-Prozesse: $($laufend.Count)"
Write-Host "Die Kopplung ist unberuehrt - sie haengt am Datensatz und am Token, nicht am Programmstand."
