<#
.SYNOPSIS
  EIN Befehl fuer jeden neuen Automaten: Agent installieren, einrichten, Waechter, Bilder, Pruefung.
.DESCRIPTION
  Gedacht fuer jemanden ohne Technikkenntnisse. Im CRM (Kundenakte -> "PC einrichten") steht
  der fertige Befehl mit dem richtigen Code. Ablauf:
    1. Pruefen, ob PowerShell als Administrator laeuft.
    2. Skripte nach C:\liftpic\setup laden.
    3. Die eigentliche Arbeit als Windows-Aufgabe (SYSTEM) starten. Sie laeuft weiter, auch wenn
       AnyDesk getrennt oder der Benutzer abgemeldet wird.
    4. Fortschritt anzeigen und am Ende gross FERTIG oder FEHLER.
  Ob der Kunde QR-Codes nutzt, kommt aus der Kopplung (UPLOAD_SOURCE=qrcode), nicht aus einem
  Schalter, den man vergessen kann. Das Verkaufsprogramm wird nur bei QR-Kunden und nur in der
  sichtbaren Sitzung neu gestartet - als SYSTEM gestartet waere es fuer die Gaeste unsichtbar.
.EXAMPLE
  .\setup.ps1 -Code 8B1136BB
#>
param(
  [Parameter(Mandatory = $true)][string]$Code,
  [switch]$Phase2,
  [string]$Ref = "main"
)

$Dir = "C:\liftpic\setup"
$Log = Join-Path $Dir "setup.log"
$Stand = Join-Path $Dir "stand.txt"
$Base = "https://raw.githubusercontent.com/john123-05/testsoftware/$Ref/scripts"
$Aufgabe = "LiftpicEinrichtung"
$Skripte = @("setup.ps1", "install_liftpic_sync_bootstrap.ps1", "einrichten_nach_install.ps1", "bilder_export.ps1", "anlagenpruefung.ps1")

function Schreibe([string]$text) { Set-Content -Path $Stand -Value $text -Encoding UTF8 }

function Gross([string]$text, [string]$farbe) {
  Write-Host ""
  Write-Host ("=" * 62) -ForegroundColor $farbe
  Write-Host "   $text" -ForegroundColor $farbe
  Write-Host ("=" * 62) -ForegroundColor $farbe
  Write-Host ""
}

function EnvWert([string]$text, [string]$name) {
  if ($text -match "(?m)^$name=(.*)$") { return $Matches[1].Trim().Trim('"') }
  return ""
}

# ---------------------------------------------------------------- Teil 2: laeuft als SYSTEM
if ($Phase2) {
  Start-Transcript -Path $Log -Append | Out-Null
  try {
    Schreibe "LAEUFT: Agent wird installiert (dauert 2-10 Minuten)"
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$Dir\install_liftpic_sync_bootstrap.ps1" -PairingCode $Code

    $envDatei = "C:\liftpic\liftpic-sync\.env"
    if (-not (Test-Path $envDatei)) { throw "Agent nicht installiert - Internet am PC pruefen und den Befehl noch einmal einfuegen." }
    $envText = Get-Content $envDatei -Raw
    $slug = EnvWert $envText "PARK_SLUG"
    if (-not $slug -or $slug -eq "unknown-park") { throw "Kopplung hat nicht geklappt - im CRM einen neuen Code erzeugen und den neuen Befehl einfuegen." }
    $mitQr = (EnvWert $envText "UPLOAD_SOURCE") -eq "qrcode"

    Schreibe "LAEUFT: Einrichtung fuer $slug (Waechter, Ordner, Agent-Neustart)"
    $einrichten = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "$Dir\einrichten_nach_install.ps1", "-Slug", $slug, "-OhneViewerNeustart")
    if (-not $mitQr) { $einrichten += "-OhneQr" }
    & powershell @einrichten

    Schreibe "LAEUFT: Bilder vom Automaten einsammeln"
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$Dir\bilder_export.ps1" -Slug $slug -Ziel "C:\Users\Public\Desktop"

    Schreibe "LAEUFT: Abschlusspruefung"
    $pruefung = & powershell -NoProfile -ExecutionPolicy Bypass -File "$Dir\anlagenpruefung.ps1" 2>&1 | Out-String
    $pruefung | Out-File (Join-Path $Dir "pruefung.txt") -Encoding UTF8

    # Was am Automaten eingestellt ist - das CRM bekommt den Bildcode zusaetzlich vom Agenten.
    $xml = EnvWert (Get-Content $envDatei -Raw) "VIEWER_SETTINGS_XML"
    $bildcode = ""; $preis = ""
    if ($xml -and (Test-Path $xml)) {
      $x = Get-Content $xml -Raw
      if ($x -match "<CustomerNumber>(\d+)</CustomerNumber>") { $bildcode = $Matches[1] }
      if ($x -match "<PricePrint>([\d.,]+)</PricePrint>") { $preis = $Matches[1] }
    }
    $agentLaeuft = $pruefung -match "genau ein Agent"
    $waechter = [bool](Get-ScheduledTask -TaskName "LiftpicSyncWatchdog" -ErrorAction SilentlyContinue)
    $zeilen = @(
      "FERTIG",
      "Park: $slug",
      "QR-Code: $(if ($mitQr) { 'ja' } else { 'nein (bleibt wie er ist)' })",
      "Bildcode am Automaten: $(if ($bildcode) { $bildcode } else { 'nicht gefunden' })",
      "Preis am Automaten: $(if ($preis) { $preis } else { 'nicht gefunden' })",
      "Agent laeuft: $(if ($agentLaeuft) { 'ja' } else { 'NEIN' })",
      "Waechter: $(if ($waechter) { 'ja' } else { 'NEIN' })",
      "Bilder: auf dem Desktop ($slug-bilder.zip)"
    )
    if (-not $agentLaeuft -or -not $waechter) { $zeilen[0] = "FEHLER: Agent oder Waechter laeuft nicht - Screenshot an John schicken." }
    Set-Content -Path $Stand -Value $zeilen -Encoding UTF8
  } catch {
    Schreibe "FEHLER: $($_.Exception.Message)"
  } finally {
    Stop-Transcript | Out-Null
    Unregister-ScheduledTask -TaskName $Aufgabe -Confirm:$false -ErrorAction SilentlyContinue
  }
  exit 0
}

# ---------------------------------------------------------------- Teil 1: sichtbares Fenster
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
  Gross "STOPP: PowerShell bitte ALS ADMINISTRATOR oeffnen" Red
  Write-Host "  Windows-Taste druecken, 'powershell' tippen, RECHTSKLICK -> 'Als Administrator ausfuehren'."
  Write-Host "  Dann den Befehl noch einmal einfuegen."
  exit 1
}
if ($Code -notmatch '^[A-Za-z0-9]{6,12}$') { Gross "STOPP: Der Code sieht falsch aus - Befehl im CRM neu kopieren" Red; exit 1 }

Gross "Liftpictures Einrichtung startet" Cyan
New-Item -ItemType Directory -Force $Dir | Out-Null
Remove-Item $Stand -ErrorAction SilentlyContinue
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
foreach ($s in $Skripte) {
  try { Invoke-WebRequest -UseBasicParsing -OutFile (Join-Path $Dir $s) "$Base/$s" }
  catch { Gross "STOPP: Kein Internet am PC (Download fehlgeschlagen)" Red; exit 1 }
}

$aktion = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Dir\setup.ps1`" -Code $Code -Phase2 -Ref $Ref"
Register-ScheduledTask -TaskName $Aufgabe -Action $aktion -User "SYSTEM" -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName $Aufgabe

Write-Host "  Laeuft jetzt im Hintergrund. Wenn AnyDesk getrennt wird: egal, es laeuft weiter." -ForegroundColor Green
Write-Host "  Fenster am besten offen lassen - hier steht gleich FERTIG." -ForegroundColor Green
Write-Host ""

$letzte = ""
$ende = (Get-Date).AddMinutes(30)
while ((Get-Date) -lt $ende) {
  Start-Sleep -Seconds 3
  if (-not (Test-Path $Stand)) { continue }
  $inhalt = @(Get-Content $Stand -ErrorAction SilentlyContinue)
  if (-not $inhalt) { continue }
  $erste = $inhalt[0]
  if ($erste -ne $letzte) { Write-Host "  $(Get-Date -Format HH:mm:ss)  $erste"; $letzte = $erste }
  if ($erste -like "FERTIG*") {
    if (($inhalt -join "`n") -match "QR-Code: ja") {
      # Neuer QR-Link wird erst nach einem Neustart des Verkaufsprogramms gedruckt - in DIESER Sitzung.
      $viewer = Get-Process | Where-Object { $_.Path -like "C:\liftpic\*" -and $_.Name -like "PhotoViewer*" -and $_.Name -notlike "*Watchdog*" } | Select-Object -First 1
      if ($viewer) {
        $pfad = $viewer.Path
        Stop-Process -Id $viewer.Id -Force
        Start-Sleep -Seconds 3
        Start-Process -FilePath $pfad -WorkingDirectory (Split-Path $pfad)
        Write-Host "  Verkaufsprogramm neu gestartet (neuer QR-Code)."
      }
    }
    Gross "FERTIG - alles eingerichtet" Green
    $inhalt | Select-Object -Skip 1 | ForEach-Object { Write-Host "   $_" }
    Write-Host ""
    Write-Host "   Diesen Bildschirm als Screenshot schicken oder im CRM 'Bildcode uebernehmen' klicken." -ForegroundColor Cyan
    exit 0
  }
  if ($erste -like "FEHLER*") {
    Gross "FEHLER" Red
    Write-Host "   $erste"
    Write-Host "   Protokoll: $Log"
    exit 1
  }
}
Gross "Dauert ungewoehnlich lange - Screenshot an John schicken" Yellow
Write-Host "   Protokoll: $Log"
