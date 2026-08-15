param(
  [string]$InstallDir = "C:\liftpic\liftpic-sync",
  [string]$EnvFile = "C:\liftpic\liftpic-sync\.env"
)

$ErrorActionPreference = "Stop"

# Warum hier so viel aufgeraeumt wird (F-029)
# ------------------------------------------
# Dienst und geplante Aufgabe liegen unter Windows in GETRENNTEN Namensraeumen.
# Beide hiessen "LiftpicSync", und das Aufraeumen suchte nur per Get-Service
# nach einem Dienst. Wer erst den Bootstrap-Installer (Aufgabe, SYSTEM,
# AtStartup) und spaeter dieses Skript mit vorhandenem nssm.exe ausfuehrte,
# hatte danach BEIDES: ab dem naechsten Neustart liefen zwei Agenten auf
# derselben Datenbank, derselben .env und denselben Fotoordnern.
#
# Das ist der Weg, auf dem der Doppelbetrieb ueberhaupt entsteht. Deshalb wird
# jetzt immer die jeweils andere Startart mit abgeraeumt, und laufende Prozesse
# werden vorher beendet - nicht nur angehalten.

if (!(Test-Path $InstallDir)) {
  New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
}

# Das venv bevorzugen. `python` aus dem PATH ist auf einem Automaten haeufig
# gar nicht vorhanden, weil Python nur ins venv installiert wurde.
$venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
  $python = $venvPython
} else {
  $python = (Get-Command python -ErrorAction Stop).Source
  Write-Warning "venv-Python nicht gefunden, nehme $python"
}

$arguments   = "-m liftpic_sync.cli run --env `"$EnvFile`""
$serviceName = "LiftpicSync"


function Stop-RunningAgents {
  <#
    Laufende Agenten beenden und WARTEN, bis sie wirklich weg sind.

    Der venv-Starter hat den echten Interpreter als Kindprozess; ein blosses
    Stop-ScheduledTask kehrt sofort zurueck, ohne dass beide beendet sind.
    Startet man in dem Moment neu, laeuft der Enkel weiter - genau die Lage,
    gegen die die Sperre gebaut wurde.
  #>
  $gefunden = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -like "*liftpic_sync*" })
  if (-not $gefunden) { return }

  Write-Host "Beende $($gefunden.Count) laufende(n) Agenten..."
  foreach ($p in $gefunden) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
  }

  for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    $rest = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
              Where-Object { $_.CommandLine -like "*liftpic_sync*" })
    if (-not $rest) { Write-Host "  alle beendet."; return }
  }
  throw "Es laeuft noch ein Agent. Abbruch, statt einen zweiten danebenzustellen."
}


function Remove-OtherStartMethods {
  param([string]$Behalten)   # 'service' oder 'task'

  if ($Behalten -ne "service") {
    $vorhanden = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($vorhanden) {
      Write-Warning "Es gibt bereits einen DIENST $serviceName - wird entfernt, sonst laufen zwei Agenten."
      $n = Get-Command nssm.exe -ErrorAction SilentlyContinue
      if ($n) {
        & $n.Source stop $serviceName 2>$null | Out-Null
        & $n.Source remove $serviceName confirm 2>$null | Out-Null
      } else {
        & sc.exe stop $serviceName   2>$null | Out-Null
        & sc.exe delete $serviceName 2>$null | Out-Null
      }
      Start-Sleep -Seconds 2
    }
  }

  if ($Behalten -ne "task") {
    # Auch Aufgaben mit anderem Namen erwischen, die denselben Agenten starten.
    $aufgaben = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
      $_.Actions.Execute -like "*python*" -and $_.Actions.Arguments -like "*liftpic_sync*"
    })
    foreach ($a in $aufgaben) {
      Write-Warning "Es gibt bereits die AUFGABE $($a.TaskName) - wird entfernt, sonst laufen zwei Agenten."
      Stop-ScheduledTask -TaskName $a.TaskName -ErrorAction SilentlyContinue
      Unregister-ScheduledTask -TaskName $a.TaskName -Confirm:$false -ErrorAction SilentlyContinue
    }
  }
}


Stop-RunningAgents

$nssm = Get-Command nssm.exe -ErrorAction SilentlyContinue
if ($nssm) {
  Remove-OtherStartMethods -Behalten "service"

  if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
    & $nssm.Source stop $serviceName | Out-Null
    & $nssm.Source remove $serviceName confirm | Out-Null
    Start-Sleep -Seconds 2
  }

  & $nssm.Source install $serviceName $python $arguments | Out-Null
  & $nssm.Source set $serviceName AppDirectory $InstallDir | Out-Null
  & $nssm.Source set $serviceName Start SERVICE_AUTO_START | Out-Null
  & $nssm.Source start $serviceName | Out-Null
  Write-Host "Dienst $serviceName eingerichtet (nssm)."
} else {
  Write-Warning "nssm.exe nicht gefunden, richte stattdessen eine geplante Aufgabe ein."
  Remove-OtherStartMethods -Behalten "task"

  $action  = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $InstallDir
  $trigger = New-ScheduledTaskTrigger -AtLogOn
  Register-ScheduledTask -TaskName $serviceName -Action $action -Trigger $trigger `
    -Description "Liftpic Sync fallback task" -Force | Out-Null
  Start-ScheduledTask -TaskName $serviceName
  Write-Host "Aufgabe $serviceName eingerichtet."
}

# Zur Kontrolle: es darf genau einer laufen.
Start-Sleep -Seconds 5
$laufend = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -like "*liftpic_sync*" })
Write-Host ""
Write-Host "Laufende Agenten-Prozesse: $($laufend.Count) (Starter + Interpreter = ein Agent)"
foreach ($p in $laufend) { Write-Host "  PID $($p.ProcessId)" }
