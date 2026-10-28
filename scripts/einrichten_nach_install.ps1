<#
.SYNOPSIS
  Nach dem Bootstrap-Installer: Automat fertig einrichten.
.DESCRIPTION
  Was bei Weissenfels und Tom der Tiger (28.10.2026) jedes Mal von Hand noetig war,
  in einem Lauf:
    * Pfade fuer Settings.xml, Muenzbestand und Muenzprotokolle in die .env,
      sofern die Dateien auf dem PC liegen (sonst bleibt der Schluessel leer).
    * SPEED_LOG_FILE aus Speedshot.ini ([SpeedLog] Filename=), wenn die
      Geschwindigkeit nicht im Dateinamen steht (SaveInfoToImageFilename=0).
    * PROBE_SKIP_PROGRAMS fuer Kamera-/Lichtschranken-Software, die auf
      diesem PC gar nicht laeuft (Kamera separat).
    * QR-Ziel in der Settings.xml auf https://liftpictures-fotos.de/<Slug>/claim?code=
      (Sicherung daneben, Latin-1 bytegenau), danach das Verkaufsprogramm hart
      neu starten - sonst gilt der neue QR erst nach dem naechsten Neustart.
    * Agent neu starten und pruefen, dass er wirklich laeuft (ein Start direkt
      nach dem Anhalten wird gelegentlich verworfen).
  Am Ende steht ein Bericht zum Abfotografieren.
.EXAMPLE
  .\einrichten_nach_install.ps1 -Slug doberan
#>
param(
  [Parameter(Mandatory = $true)][string]$Slug,
  [string]$InstallDir = "C:\liftpic\liftpic-sync",
  [switch]$OhneViewerNeustart
)
$ErrorActionPreference = "Stop"
$EnvPath = Join-Path $InstallDir ".env"
$VenvPy = Join-Path $InstallDir ".venv\Scripts\python.exe"
if (-not (Test-Path $EnvPath)) { throw "Keine .env unter $EnvPath - zuerst den Bootstrap-Installer ausfuehren." }
$stempel = Get-Date -Format "yyyyMMdd-HHmm"
Copy-Item $EnvPath "$EnvPath.bak-$stempel"

# ------------------------------------------------------------ 1/4 Quellen finden
Write-Host "1/4 Suche Zahlungs- und Speed-Quellen..."
$werte = [ordered]@{}
$settings = "C:\liftpic\samuel_neu\Settings.xml"
if (Test-Path $settings) { $werte["VIEWER_SETTINGS_XML"] = $settings }
$coinStats = "C:\liftpic\samuel_neu\CoinStats.txt"
if (Test-Path $coinStats) { $werte["COIN_STATS_FILE"] = $coinStats }
if (Get-ChildItem "C:\liftpic\samuel_neu\Log" -Filter "NRI.CoinCharger_*.txt" -ErrorAction SilentlyContinue | Select-Object -First 1) {
  $werte["COIN_LOG_GLOB"] = "C:\liftpic\samuel_neu\Log\NRI.CoinCharger_*.txt"
}

foreach ($ini in @("C:\liftpic\3GerTis\Speedshot.ini", "C:\liftpic\speedshot\Speedshot.ini")) {
  if (-not (Test-Path $ini)) { continue }
  $abschnitt = ""
  $imNamen = $null
  $logDatei = $null
  foreach ($zeile in Get-Content $ini) {
    $z = $zeile.Trim()
    if ($z -match '^\[(.+)\]$') { $abschnitt = $Matches[1]; continue }
    if ($z -match '^SaveInfoToImageFilename\s*=\s*(\d)') { $imNamen = $Matches[1] }
    if ($abschnitt -eq "SpeedLog" -and $z -match '^Filename\s*=\s*(.+)$') { $logDatei = $Matches[1].Trim() }
  }
  if ($imNamen -ne "1" -and $logDatei -and (Test-Path $logDatei)) {
    $werte["SPEED_LOG_FILE"] = $logDatei
    break
  }
}

$laeuft = @(Get-Process | ForEach-Object { $_.Name })
$skip = @()
if (-not ($laeuft | Where-Object { $_ -match '^(3gerTis|camera26)' })) { $skip += "Kamera-Software" }
if (-not ($laeuft | Where-Object { $_ -match '^(AidaTest|Speedshot)' })) { $skip += "Lichtschranke" }
if ($skip.Count) { $werte["PROBE_SKIP_PROGRAMS"] = ($skip -join ",") }

$zeilen = @(Get-Content $EnvPath | Where-Object { -not $werte.Contains((($_ -split '=', 2)[0]).Trim()) })
foreach ($k in $werte.Keys) { $zeilen += "$k=$($werte[$k])" }
[IO.File]::WriteAllLines($EnvPath, $zeilen)

# ------------------------------------------------------------ 2/4 QR-Ziel
Write-Host "2/4 QR-Ziel..."
$qrNeu = "https://liftpictures-fotos.de/$Slug/claim?code="
$qrAlt = $null
$qrGeaendert = $false
if (Test-Path $settings) {
  $enc = [Text.Encoding]::GetEncoding(28591)
  $text = $enc.GetString([IO.File]::ReadAllBytes($settings))
  $m = [regex]::Match($text, '<QrCodeBeginningString>([^<]*)</QrCodeBeginningString>')
  if ($m.Success) {
    $qrAlt = $m.Groups[1].Value
    if ($qrAlt -ne $qrNeu) {
      Copy-Item $settings "$settings.bak-$stempel"
      $g = $m.Groups[1]
      $text = $text.Substring(0, $g.Index) + $qrNeu + $text.Substring($g.Index + $g.Length)
      [IO.File]::WriteAllBytes($settings, $enc.GetBytes($text))
      $qrGeaendert = $true
    }
  }
}

# ------------------------------------------------------------ 3/4 Verkaufsprogramm
if ($qrGeaendert -and -not $OhneViewerNeustart) {
  Write-Host "3/4 Starte das Verkaufsprogramm neu (neuer QR)..."
  $v = Get-Process -Name "PhotoViewerFacebook*" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($v -and $v.Path) {
    $exe = $v.Path
    # Hart beenden: beim normalen Schliessen koennte es die alte Adresse zurueckschreiben.
    Stop-Process -Id $v.Id -Force
    Start-Sleep -Seconds 15
    if (-not (Get-Process -Name "PhotoViewerFacebook*" -ErrorAction SilentlyContinue)) {
      Start-Process $exe -WorkingDirectory (Split-Path $exe)
    }
  } else {
    Write-Warning "Verkaufsprogramm laeuft nicht - der neue QR gilt ab dem naechsten Start."
  }
} else {
  Write-Host "3/4 Verkaufsprogramm: kein Neustart noetig."
}

# ------------------------------------------------------------ 4/4 Agent
Write-Host "4/4 Starte den Agenten neu..."
function Get-Agenten {
  @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*liftpic_sync*" })
}
Stop-ScheduledTask -TaskName LiftpicSync -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5
Get-Agenten | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3
$agenten = @()
for ($i = 1; $i -le 3 -and $agenten.Count -eq 0; $i++) {
  Start-ScheduledTask -TaskName LiftpicSync
  for ($j = 0; $j -lt 20 -and $agenten.Count -eq 0; $j++) {
    Start-Sleep -Seconds 1
    $agenten = Get-Agenten
  }
}

# ------------------------------------------------------------ Bericht
Write-Host ""
Write-Host "================================================================"
Write-Host " EINRICHTUNG $Slug - $(Get-Date -Format 'dd.MM.yyyy HH:mm')"
Write-Host "================================================================"
Write-Host "Eingetragen:"
foreach ($k in $werte.Keys) { Write-Host "  $k=$($werte[$k])" }
if (-not $werte.Contains("SPEED_LOG_FILE")) { Write-Host "  (kein Speedshot-Protokoll gefunden)" }
if ($null -eq $qrAlt) { Write-Host "QR: keine Settings.xml / kein QrCodeBeginningString gefunden" }
elseif ($qrGeaendert) { Write-Host "QR: $qrAlt  ->  $qrNeu" }
else { Write-Host "QR: stand schon richtig ($qrNeu)" }
if (Test-Path $settings) {
  Select-String -Path $settings -Pattern '<(PricePrint|PriceEmail|EnablePrint|EnableEmail|EnableCreditCardPayment)>' |
    ForEach-Object { Write-Host "  $($_.Line.Trim())" }
}
$viewer = Get-Process -Name "PhotoViewerFacebook*" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($viewer) { Write-Host "Verkaufsprogramm: laeuft seit $($viewer.StartTime)" } else { Write-Host "Verkaufsprogramm: laeuft NICHT" }
Write-Host "Programme aus C:\liftpic:"
Get-Process | Where-Object { $_.Path -like 'C:\liftpic\*' -and $_.Path -notlike '*liftpic-sync*' } |
  Sort-Object Name -Unique | ForEach-Object { Write-Host "  $($_.Name)  $($_.Path)" }
if (Test-Path $VenvPy) { & $VenvPy -m liftpic_sync.cli preflight --env $EnvPath }
Write-Host ""
if ($agenten.Count) {
  Write-Host "Agent laeuft ($($agenten.Count) Prozesse). Fertig." -ForegroundColor Green
} else {
  Write-Warning "Der Agent laeuft NICHT. Von Hand: Start-ScheduledTask LiftpicSync"
}
