param(
  [string]$InstallDir     = "C:\liftpic\liftpic-sync",
  [string]$Ausfall        = "",
  [int]   $FensterMinuten = 60
)

# Spurensuche nach einem Verbindungsabbruch
# ----------------------------------------
# Rein lesend. Aendert nichts, darf im laufenden Betrieb laufen, braucht aber
# Administratorrechte - sonst bleiben Ereignisprotokoll und ein erhoeht
# laufender Agent unsichtbar (F-033).
#
# Beantwortet die eine Frage, die man von aussen nicht beantworten kann:
# Ist der AGENT gestorben, oder war das NETZ weg? Der Server sieht in beiden
# Faellen nur, dass nichts mehr kommt - das sind aber zwei ganz verschiedene
# Baustellen.
#
# Aufruf mit eigenem Zeitpunkt:
#   .\ausfall_spurensuche.ps1 -Ausfall "2026-08-18 08:49"

$ErrorActionPreference = "Continue"

if ([string]::IsNullOrWhiteSpace($Ausfall)) {
  $zeitpunkt = (Get-Date).Date.AddHours(8).AddMinutes(49)
} else {
  $zeitpunkt = [datetime]::Parse($Ausfall)
}
$von = $zeitpunkt.AddMinutes(-$FensterMinuten)
$bis = $zeitpunkt.AddMinutes($FensterMinuten)

function Kopf($text) {
  Write-Output ""
  Write-Output ("=" * 70)
  Write-Output ("  " + $text)
  Write-Output ("=" * 70)
}

Write-Output ""
Write-Output "Spurensuche Verbindungsabbruch"
Write-Output ("Ausfallzeitpunkt : " + $zeitpunkt.ToString("dd.MM.yyyy HH:mm:ss"))
Write-Output ("Fenster          : " + $von.ToString("HH:mm") + " bis " + $bis.ToString("HH:mm"))
Write-Output ("Rechner          : " + $env:COMPUTERNAME)
Write-Output ("Jetzt            : " + (Get-Date).ToString("dd.MM.yyyy HH:mm:ss"))

# ---------------------------------------------------------------------------
Kopf "1. Laeuft der Agent JETZT, und seit wann?"
# "Seit wann" ist die wichtigste Zahl des ganzen Skripts.
$prozesse = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    ($_.Name -eq "python.exe" -or $_.Name -eq "pythonw.exe") -and
    (("" + $_.CommandLine) -like "*liftpic*" -or ("" + $_.ExecutablePath) -like "*liftpic*")
  }
if ($prozesse) {
  foreach ($p in $prozesse) {
    $start = $p.CreationDate
    $dauer = [math]::Round(((Get-Date) - $start).TotalMinutes)
    Write-Output ("  PID " + $p.ProcessId + "  gestartet " + $start.ToString("dd.MM.yyyy HH:mm:ss") + "  (seit " + $dauer + " min)")
    Write-Output ("      " + $p.ExecutablePath)
  }
  Write-Output ""
  Write-Output "  Hinweis: venv-Starter und echter Interpreter sind ZUSAMMEN ein"
  Write-Output "  Agent. Zwei Eintraege sind normal, drei waeren zu viel."
} else {
  Write-Output "  KEIN Agent laeuft. Das ist bereits der Befund."
}

# ---------------------------------------------------------------------------
Kopf "2. Faengt ihn ueberhaupt jemand auf? (Autostart)"
$aufgaben = schtasks /query /fo csv 2>$null | Select-String -Pattern "liftpic" -SimpleMatch
if ($aufgaben) { $aufgaben | ForEach-Object { Write-Output ("  " + $_.Line) } }
else           { Write-Output "  Keine geplante Aufgabe mit 'liftpic' gefunden." }
$dienst = Get-Service -Name "LiftpicSync" -ErrorAction SilentlyContinue
if ($dienst) { Write-Output ("  Dienst LiftpicSync: " + $dienst.Status + " / Start=" + $dienst.StartType) }
else         { Write-Output "  Kein Dienst 'LiftpicSync'." }
Write-Output ""
Write-Output "  Es muss GENAU EINE Startart geben. Keine heisst: nach einem Absturz"
Write-Output "  bleibt er liegen (F-038). Zwei heissen: doppelter Betrieb."

# ---------------------------------------------------------------------------
Kopf "3. Was sagt das Agent-Protokoll im Ausfallfenster?"
$logs = @()
foreach ($ort in @("$InstallDir\logs", "$InstallDir", "C:\liftpic\logs")) {
  if (Test-Path $ort) {
    $logs += Get-ChildItem $ort -Filter "*.log" -File -ErrorAction SilentlyContinue
  }
}
$logs = $logs | Sort-Object LastWriteTime -Descending | Select-Object -First 3
if (-not $logs) {
  Write-Output "  Kein Protokoll gefunden. Gesucht in:"
  Write-Output ("    " + $InstallDir + "\logs")
  Write-Output ("    " + $InstallDir)
  Write-Output "    C:\liftpic\logs"
} else {
  foreach ($log in $logs) {
    Write-Output ""
    Write-Output ("  --- " + $log.FullName)
    Write-Output ("      zuletzt geschrieben " + $log.LastWriteTime.ToString("dd.MM.yyyy HH:mm:ss"))
    # Die entscheidende Frage: HOERT das Protokoll zum Ausfallzeitpunkt auf?
    # Hoert es auf  -> der Agent ist gestorben.
    # Laeuft es weiter -> der Agent lebte, das Netz war weg.
    # Alles andere ist Beiwerk, deshalb wird hier nicht das ganze Protokoll
    # ausgeschuettet, sondern nur der Rand der Luecke plus alles Auffaellige.
    $letzteDavor = $null
    $ersteDanach = $null
    $auffaellig  = @()
    # Bewusst eng gefasst. Der erste Entwurf traf "restart_needed" in JEDER
    # Routinezeile und lieferte 258 Treffer reinen Rauschens.
    $muster  = "ERROR|WARNING|CRITICAL|Traceback|Exception|" +
               "401|403|refused|timed out|unreachable|Max retries"
    $rauschen = "rides seen="

    $leser = [System.IO.File]::Open($log.FullName, "Open", "Read", "ReadWrite")
    $sr = New-Object System.IO.StreamReader($leser)
    while (-not $sr.EndOfStream) {
      $zeile = $sr.ReadLine()
      if ($zeile -match "(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})") {
        $t = [datetime]::MinValue
        if ([datetime]::TryParse($matches[1], [ref]$t)) {
          if ($t -le $zeitpunkt) { $letzteDavor = $zeile }
          if ($t -gt $zeitpunkt -and -not $ersteDanach) { $ersteDanach = $zeile }
          if ($t -ge $von -and $t -le $bis -and
              $zeile -match $muster -and $zeile -notmatch $rauschen) {
            $auffaellig += $zeile
          }
        }
      }
    }
    $sr.Close(); $leser.Close()

    Write-Output ""
    Write-Output "      LETZTE Zeile bis zum Ausfallzeitpunkt:"
    if ($letzteDavor) { Write-Output ("        " + $letzteDavor) }
    else              { Write-Output "        (keine)" }
    Write-Output "      ERSTE Zeile danach:"
    if ($ersteDanach) { Write-Output ("        " + $ersteDanach) }
    else              { Write-Output "        (keine - das Protokoll endet hier. Der Agent hat aufgehoert zu schreiben.)" }

    if ($auffaellig.Count -gt 0) {
      Write-Output ""
      Write-Output ("      Auffaellige Zeilen im Fenster (" + $auffaellig.Count + " gefunden, letzte 25):")
      $auffaellig | Select-Object -Last 25 | ForEach-Object { Write-Output ("        " + $_) }
    } else {
      Write-Output ""
      Write-Output "      Keine Fehler, Warnungen oder Start/Stop-Meldungen im Fenster."
    }
  }
}

# ---------------------------------------------------------------------------
Kopf "4. Hat der RECHNER etwas gemacht? (Neustart, Standby, Absturz)"
# 41   Kernel-Power: Rechner war unsauber aus - Strom weg oder haengengeblieben
# 42   Rechner geht in den Standby
# 1074 jemand oder etwas hat Neustart/Herunterfahren ausgeloest
# 6005 Ereignisprotokoll gestartet (= Rechner hochgefahren)
# 6006 sauber beendet
# 6008 letztes Herunterfahren war unerwartet
try {
  $ereignisse = Get-WinEvent -FilterHashtable @{
    LogName = "System"; Id = 41,42,1074,6005,6006,6008; StartTime = $von.AddHours(-12); EndTime = $bis
  } -ErrorAction Stop | Sort-Object TimeCreated
  if ($ereignisse) {
    foreach ($e in $ereignisse) {
      $txt = ($e.Message -split "`r?`n")[0]
      Write-Output ("  " + $e.TimeCreated.ToString("dd.MM. HH:mm:ss") + "  [" + $e.Id + "] " + $txt)
    }
  } else {
    Write-Output "  Nichts. Der Rechner lief durch - kein Neustart, kein Standby."
  }
} catch {
  # Get-WinEvent wirft, wenn NICHTS gefunden wurde - das ist kein Fehler,
  # sondern die Entwarnung. Die beiden Faelle muss man auseinanderhalten.
  if ($_.Exception.Message -match "No events were found|keine Ereignisse gefunden") {
    Write-Output "  Nichts. Der Rechner lief durch - kein Neustart, kein Standby."
  } else {
    Write-Output ("  Ereignisprotokoll nicht lesbar: " + $_.Exception.Message)
    Write-Output "  Laeuft dieses Fenster wirklich als Administrator?"
  }
}

# ---------------------------------------------------------------------------
Kopf "5. Fehler und Warnungen des Systems im Ausfallfenster"
# Hier taucht auf, wenn die Netzwerkkarte zurueckgesetzt wurde, das WLAN abriss
# oder ein Treiber sich verschluckt hat.
try {
  $sys = Get-WinEvent -FilterHashtable @{
    LogName = "System"; Level = 1,2,3; StartTime = $von; EndTime = $bis
  } -ErrorAction Stop | Sort-Object TimeCreated | Select-Object -First 30
  if ($sys) {
    foreach ($e in $sys) {
      $txt = ($e.Message -split "`r?`n")[0]
      if ($txt.Length -gt 110) { $txt = $txt.Substring(0, 110) + "..." }
      Write-Output ("  " + $e.TimeCreated.ToString("HH:mm:ss") + "  " + $e.ProviderName + ": " + $txt)
    }
  } else {
    Write-Output "  Keine Fehler oder Warnungen in diesem Fenster."
  }
} catch {
  if ($_.Exception.Message -match "No events were found|keine Ereignisse gefunden") {
    Write-Output "  Keine Fehler oder Warnungen in diesem Fenster."
  } else {
    Write-Output ("  nicht lesbar: " + $_.Exception.Message)
  }
}

# ---------------------------------------------------------------------------
Kopf "6. Darf der Rechner schlafen gehen?"
# Ein Automat, der in den Standby faellt oder dessen Netzwerkkarte abgeschaltet
# wird, sieht von aussen exakt wie ein toter Agent aus.
Write-Output ("  " + (powercfg /getactivescheme 2>$null))
Write-Output ""
Write-Output "  Standby nach Leerlauf (0x0 = nie, alles andere ist verdaechtig):"
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>$null |
  Select-String -Pattern "0x" | ForEach-Object { Write-Output ("    " + $_.Line.Trim()) }
Write-Output ""
Write-Output "  Festplatte abschalten nach Leerlauf:"
powercfg /query SCHEME_CURRENT SUB_DISK DISKIDLE 2>$null |
  Select-String -Pattern "0x" | ForEach-Object { Write-Output ("    " + $_.Line.Trim()) }
Write-Output ""
Write-Output "  Netzwerkkarten, die Windows abschalten darf:"
$strom = Get-CimInstance -ClassName MSPower_DeviceEnable -Namespace root\wmi -ErrorAction SilentlyContinue |
  Where-Object { $_.Enable -eq $true } | Select-Object -First 8
if ($strom) { $strom | ForEach-Object { Write-Output ("    " + $_.InstanceName) } }
else        { Write-Output "    keine gefunden oder nicht lesbar" }

# ---------------------------------------------------------------------------
Kopf "Fertig - so liest man das Ergebnis"
Write-Output "  Agent laeuft seit VOR dem Ausfall  -> das Netz war weg, nicht der Agent."
Write-Output "  Agent gestartet NACH dem Ausfall   -> er ist gestorben und neu gestartet."
Write-Output "  Kein Agent und kein Autostart      -> F-038, niemand hat ihn aufgefangen."
Write-Output "  Ereignis 41 oder 6008 im Fenster   -> Strom weg oder Rechner haengengeblieben."
Write-Output "  Ereignis 42 plus spaeterer Start   -> der Rechner war im Standby."
Write-Output "  Nichts von alledem                 -> Leitung oder Router, nicht der PC."
Write-Output ""
Write-Output "Ausgabe bitte komplett kopieren und weitergeben."
Write-Output ""
