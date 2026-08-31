<#
.SYNOPSIS
  Ein 5-Minuten-Wächter, der den Agenten neu startet, falls er tot ist.

.DESCRIPTION
  Warum das nötig ist
  -------------------
  Das `python.exe` im venv ist ein Starter-Stub: er beendet sich mit Code 0,
  sobald er den echten Interpreter gestartet hat. Für Task Scheduler ist die
  Aufgabe damit im selben Moment "erfolgreich beendet" - und die eingebaute
  Selbstheilung ("Bei Fehler neu starten") greift nur bei einem FEHLER, nicht
  bei Erfolg. Stirbt der echte Interpreter danach (Absturz beim Booten, ehe
  Netz/Kamera bereit sind), startet ihn nichts mehr.

  Am 31.08.2026 stand der Imster Uploader deshalb nach dem 08:49-Neustart
  über eine Stunde still.

  Dieser Wächter ist die Absicherung dagegen: er prüft alle 5 Minuten, ob ein
  `liftpic_sync`-Interpreter läuft, und ruft sonst `Start-ScheduledTask
  LiftpicSync`. Er ist bewusst dumm - er fragt nicht nach dem Warum.

  Die Losverlierer-Logik im Agenten (zweiter Agent sieht, dass ein anderer die
  Zustands-DB hält, und beendet sich mit Code 0) bleibt absichtlich so: würde
  sie mit Code 1 enden, drehte die Selbstheilung eine Neustart-Schleife im
  Minutentakt, solange ein gesunder Agent läuft.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\watchdog_einrichten.ps1
#>
param(
  [string]$InstallDir = "C:\liftpic\liftpic-sync",
  [string]$Aufgabe    = "LiftpicSync",
  [string]$WatchdogSkript = "C:\liftpic\watchdog.ps1",
  [int]$IntervallMinuten = 5
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Bitte als Administrator ausfuehren."
}

$inhalt = @"
# Von watchdog_einrichten.ps1 erzeugt. Prueft, ob der Agent laeuft; sonst Neustart.
`$laeuft = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -EA SilentlyContinue |
  Where-Object { `$_.CommandLine -like '*liftpic_sync*' }
if (-not `$laeuft) {
  Start-ScheduledTask -TaskName '$Aufgabe'
}
"@
Set-Content -Path $WatchdogSkript -Value $inhalt -Encoding ASCII
Write-Host "Watchdog-Skript geschrieben: $WatchdogSkript"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchdogSkript`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes $IntervallMinuten)
Register-ScheduledTask -TaskName "$($Aufgabe)Watchdog" -Force `
  -User "SYSTEM" -RunLevel Highest -Action $action -Trigger $trigger `
  -Description "Startet $Aufgabe neu, falls kein Agent laeuft (venv-Starter-Stub umgeht die Selbstheilung)." | Out-Null

Write-Host "Aufgabe $($Aufgabe)Watchdog eingerichtet - prueft alle $IntervallMinuten Minuten."
Write-Host ""
Write-Host "Kontrolle:  Get-ScheduledTask -TaskName $($Aufgabe)Watchdog"
