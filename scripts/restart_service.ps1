$ErrorActionPreference = "Stop"
$serviceName = "LiftpicSync"

# Anhalten, WARTEN, pruefen, erst dann starten (F-029).
#
# Frueher standen Stop und Start direkt untereinander. Stop-ScheduledTask kehrt
# sofort zurueck, ohne dass der Prozess wirklich beendet ist - und der
# venv-Starter hat den echten Interpreter als Kindprozess. Wer in dem Moment
# neu startet, hat den Enkel des alten Laufs neben dem neuen Agenten stehen.
#
# Das `-ErrorAction SilentlyContinue` beim Anhalten verschluckte zusaetzlich
# jeden Fehlschlag: schlug das Stoppen fehl, wurde trotzdem gestartet.

function Wait-AgentsGone {
  param([int]$Sekunden = 15)
  for ($i = 0; $i -lt ($Sekunden * 2); $i++) {
    $rest = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
              Where-Object { $_.CommandLine -like "*liftpic_sync*" })
    if (-not $rest) { return $true }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

# Beide Startarten pruefen, nicht nur die erste. Existieren beide, ist das
# bereits der Doppelbetrieb - dann sagen wir es, statt nur eine anzufassen.
$dienst   = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
$aufgabe  = Get-ScheduledTask -TaskName $serviceName -ErrorAction SilentlyContinue

if ($dienst -and $aufgabe) {
  Write-Warning "ACHTUNG: Es gibt einen Dienst UND eine Aufgabe namens $serviceName."
  Write-Warning "Das sind zwei Agenten auf derselben Datenbank."
  Write-Warning "Bitte scripts\install_windows_service.ps1 ausfuehren - das raeumt die zweite Startart ab."
}

if ($dienst) {
  Stop-Service -Name $serviceName
  if (-not (Wait-AgentsGone)) {
    throw "Der alte Agent laeuft noch. Kein Neustart, sonst stuenden zwei nebeneinander."
  }
  Start-Service -Name $serviceName
  Write-Host "Dienst $serviceName neu gestartet."
} elseif ($aufgabe) {
  Stop-ScheduledTask -TaskName $serviceName
  if (-not (Wait-AgentsGone)) {
    # Die Aufgabe hat den Prozess nicht mitgenommen - dann von Hand.
    Write-Warning "Aufgabe angehalten, Prozess laeuft noch - beende ihn direkt."
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -like "*liftpic_sync*" } |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    if (-not (Wait-AgentsGone)) {
      throw "Der alte Agent laeuft weiterhin. Kein Neustart."
    }
  }
  Start-ScheduledTask -TaskName $serviceName
  Write-Host "Aufgabe $serviceName neu gestartet."
} else {
  Write-Warning "Weder Dienst noch Aufgabe $serviceName gefunden."
}
