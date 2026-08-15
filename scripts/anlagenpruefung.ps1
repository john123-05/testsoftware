<#
.SYNOPSIS
  Zustand eines Automaten auf einen Blick - rein lesend.

.DESCRIPTION
  Beantwortet die Fragen, die man sich an einer Anlage wirklich stellt:

    * Kommt der Uploader nach einem Stromausfall von selbst wieder?
    * Laeuft gerade genau einer - oder zwei?
    * Welche Programme laufen sonst noch?
    * Heilt er sich selbst, wenn er haengt?
    * Gibt es eine Sicherung, falls etwas schiefgeht?

  Aendert NICHTS: kein Start, kein Stopp, keine Datei. Darf jederzeit im
  laufenden Betrieb ausgefuehrt werden.

  Am besten ALS ADMINISTRATOR: sonst bleibt die Befehlszeile eines erhoeht
  laufenden Agenten unlesbar, und die Zaehlung wird ungenau (F-033).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\liftpic\liftpic-sync\scripts\anlagenpruefung.ps1
#>
param(
  [string]$InstallDir = "C:\liftpic\liftpic-sync"
)

$ErrorActionPreference = "Continue"

$erhoeht = ([Security.Principal.WindowsPrincipal] `
  [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

function Titel { param([string]$T) Write-Host ""; Write-Host $T -ForegroundColor Cyan }
function Zeile { param([string]$K, [string]$V, [string]$Farbe = "Gray")
  Write-Host ("  {0,-26} " -f $K) -NoNewline; Write-Host $V -ForegroundColor $Farbe }

$warnungen = @()

Write-Host ""
Write-Host "==============================================================="
Write-Host "  ANLAGENPRUEFUNG - es wird nichts veraendert"
Write-Host "  $(Get-Date -Format 'dd.MM.yyyy HH:mm:ss')"
Write-Host "==============================================================="
if (-not $erhoeht) {
  Write-Host ""
  Write-Warning "Ohne Administratorrechte. Ein Agent, der als Dienst oder als"
  Write-Warning "SYSTEM laeuft, ist dann nur teilweise sichtbar."
}


# ---------------------------------------------------- Nach dem Stromausfall
Titel "KOMMT ER NACH EINEM STROMAUSFALL WIEDER?"

$dienst   = Get-Service -Name "LiftpicSync" -ErrorAction SilentlyContinue
$aufgaben = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
  $_.Actions.Arguments -like "*liftpic_sync*" -or $_.TaskName -like "*iftpicSync*"
})

if ($dienst) {
  Zeile "Dienst" "$($dienst.Name) - $($dienst.Status), Start: $($dienst.StartType)" `
    $(if ($dienst.StartType -eq "Automatic") { "Green" } else { "Yellow" })
  if ($dienst.StartType -ne "Automatic") {
    $warnungen += "Der Dienst startet nicht automatisch - nach einem Stromausfall bleibt er aus."
  }
}

if ($aufgaben.Count -eq 0 -and -not $dienst) {
  Zeile "Autostart" "KEINER GEFUNDEN" "Red"
  $warnungen += "Weder Dienst noch Aufgabe: nach einem Stromausfall startet NICHTS von selbst."
}

foreach ($a in $aufgaben) {
  $i = Get-ScheduledTaskInfo -TaskName $a.TaskName -TaskPath $a.TaskPath -ErrorAction SilentlyContinue
  $ausloeser = ($a.Triggers | ForEach-Object { $_.CimClass.CimClassName }) -join ", "
  $beimStart = $ausloeser -match "Boot"

  Zeile "Aufgabe" $a.TaskName
  Zeile "  Zustand" $a.State $(if ($a.State -eq "Ready" -or $a.State -eq "Running") { "Green" } else { "Red" })
  Zeile "  Konto" $a.Principal.UserId
  Zeile "  Ausloeser" $ausloeser $(if ($beimStart) { "Green" } else { "Yellow" })
  if ($i) {
    Zeile "  Zuletzt gelaufen" "$($i.LastRunTime)  (Ergebnis $($i.LastTaskResult))"
  }
  # Selbstheilung: startet die Aufgabe nach einem Absturz neu?
  $neustarts = $a.Settings.RestartCount
  $abstand   = $a.Settings.RestartInterval
  if ($neustarts -gt 0) {
    Zeile "  Selbstheilung" "$neustarts Versuche, Abstand $abstand" "Green"
  } else {
    Zeile "  Selbstheilung" "aus - stuerzt er ab, bleibt er aus" "Yellow"
    $warnungen += "Die Aufgabe startet den Agenten nach einem Absturz nicht neu."
  }

  if (-not $beimStart -and $a.Principal.UserId -match "SYSTEM") {
    $warnungen += "Die Aufgabe laeuft als SYSTEM, startet aber nicht beim Hochfahren."
  }
}

if ($dienst -and $aufgaben.Count -gt 0) {
  Zeile "ACHTUNG" "Dienst UND Aufgabe vorhanden" "Red"
  $warnungen += "Es gibt einen Dienst UND eine Aufgabe - das sind zwei Agenten auf derselben Datenbank. install_windows_service.ps1 raeumt das auf."
}


# --------------------------------------------------------- Laufende Prozesse
Titel "WAS LAEUFT GERADE"

$python = @(Get-Process -Name python -ErrorAction SilentlyContinue)
$agenten = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -like "*liftpic_sync*" })

if ($agenten.Count -gt 0) {
  foreach ($p in $agenten) {
    $art = if ($p.CommandLine -like "*.venv*") { "Starter" } else { "Interpreter" }
    Zeile "Agent" "PID $($p.ProcessId) [$art] seit $($p.CreationDate)"
  }
  # Starter und Interpreter sind EIN Agent. Mehr als zwei ist verdaechtig.
  if ($agenten.Count -gt 2) {
    Zeile "Bewertung" "$($agenten.Count) Prozesse - das sind MEHRERE Agenten" "Red"
    $warnungen += "Es laufen mehrere Agenten gleichzeitig."
  } else {
    Zeile "Bewertung" "genau ein Agent (Starter + Interpreter)" "Green"
  }
} elseif ($python.Count -gt 0 -and -not $erhoeht) {
  Zeile "Agent" "$($python.Count) python.exe, Befehlszeile nicht lesbar" "Yellow"
  $warnungen += "Ohne Administratorrechte laesst sich nicht pruefen, ob es Agenten sind."
} else {
  Zeile "Agent" "KEINER LAEUFT" "Red"
  $warnungen += "Es laeuft kein Agent - es wird nichts hochgeladen."
}

foreach ($n in @("PhotoViewerFacebook!", "3gerTis_v70", "AidaTest", "easyZVT")) {
  $p = Get-Process -Name $n -ErrorAction SilentlyContinue
  if ($p) { Zeile $n "laeuft (PID $($p.Id -join ', '))" "Green" }
}


# --------------------------------------------------------- Lebt der Agent?
Titel "LEBENSZEICHEN"

$logDatei = Join-Path $InstallDir "logs\liftpic-sync.log"
if (Test-Path $logDatei) {
  $alter = (New-TimeSpan -Start (Get-Item $logDatei).LastWriteTime -End (Get-Date)).TotalSeconds
  $farbe = if ($alter -lt 120) { "Green" } elseif ($alter -lt 600) { "Yellow" } else { "Red" }
  Zeile "Protokoll geschrieben" ("vor {0:N0} Sekunden" -f $alter) $farbe
  if ($alter -ge 600) { $warnungen += "Der Agent hat seit ueber 10 Minuten nichts protokolliert." }

  $fehler = @(Get-Content $logDatei -Tail 200 -ErrorAction SilentlyContinue |
              Select-String -Pattern " ERROR ")
  Zeile "Fehler (letzte 200 Zeilen)" $fehler.Count $(if ($fehler.Count -eq 0) { "Green" } else { "Yellow" })
  if ($fehler.Count -gt 0) {
    $fehler | Select-Object -Last 3 | ForEach-Object {
      $t = $_.Line; if ($t.Length -gt 110) { $t = $t.Substring(0,110) }
      Write-Host "      $t" -ForegroundColor DarkGray
    }
  }
} else {
  Zeile "Protokoll" "nicht gefunden: $logDatei" "Red"
}

# Wachhunde aus der .env - sie beenden den Agenten, damit die Aufgabe ihn
# neu startet. Ohne Autostart waere das allerdings ein Selbstmord.
$envDatei = Join-Path $InstallDir ".env"
if (Test-Path $envDatei) {
  $envText = Get-Content $envDatei -Encoding UTF8 -ErrorAction SilentlyContinue
  foreach ($schluessel in @("WATCHDOG_SECONDS", "UPLOAD_STALL_SECONDS")) {
    $wert = ($envText | Where-Object { $_ -match "^\s*$schluessel\s*=\s*(.*)$" } |
             ForEach-Object { $Matches[1].Trim() } | Select-Object -First 1)
    if ($wert) { Zeile $schluessel $wert }
  }
  $token = ($envText | Where-Object { $_ -match "^\s*DEVICE_TOKEN\s*=\s*(.+)$" })
  Zeile "Geraetetoken" $(if ($token) { "vorhanden" } else { "FEHLT" }) `
    $(if ($token) { "Green" } else { "Red" })
  if (-not $token) { $warnungen += "Kein Geraetetoken in der .env - der Automat kann sich nicht anmelden." }
}


# -------------------------------------------------------------- Sicherungen
Titel "RUECKWEG"

$sicherungen = @(Get-ChildItem (Split-Path $InstallDir -Parent) -Directory -ErrorAction SilentlyContinue |
                 Where-Object { $_.Name -like "sicherung-liftpic-sync-*" } |
                 Sort-Object Name -Descending)
if ($sicherungen.Count -gt 0) {
  Zeile "Sicherungen" "$($sicherungen.Count) vorhanden" "Green"
  Zeile "  neueste" $sicherungen[0].FullName
} else {
  Zeile "Sicherungen" "keine" "Yellow"
  $warnungen += "Keine Ordnersicherung vorhanden - vor dem naechsten Update eine anlegen."
}


# ----------------------------------------------------------------- Ergebnis
Write-Host ""
Write-Host "==============================================================="
if ($warnungen.Count -eq 0) {
  Write-Host "  ALLES IN ORDNUNG" -ForegroundColor Green
} else {
  Write-Host "  $($warnungen.Count) PUNKT(E) ZUM ANSEHEN" -ForegroundColor Yellow
  foreach ($w in $warnungen) { Write-Host "   - $w" -ForegroundColor Yellow }
}
Write-Host "==============================================================="
Write-Host ""
