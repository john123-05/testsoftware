<#
.SYNOPSIS
  Sucht nach einem wiederkehrenden Takt hinter Verbindungsabbruechen - rein
  lesend.

.DESCRIPTION
  ausfall_spurensuche.ps1 beantwortet "was war zu DIESEM einen Zeitpunkt los".
  Dieses Skript hier beantwortet die andere Frage, die "jeden zweiten Tag"
  aufwirft: gibt es ueberhaupt einen TAKT, und wo kommt er her?

  Prueft der Reihe nach die ueblichen Verdaechtigen fuer einen periodischen
  Verbindungsabriss:

    1. DHCP-Lease - wann wurde sie zuletzt erneuert, wie lange laeuft sie?
       Ein Router, der Adressen z. B. alle 48 h neu vergibt, kappt dabei kurz
       die Verbindung. Passt die Laufzeit zum gemeldeten Rhythmus?
    2. Erneuerungs-Ereignisse des DHCP-Clients der letzten 14 Tage, mit
       Zeitabstaenden zueinander - zeigt den TATSAECHLICHEN Takt, nicht nur
       die aktuelle Lease.
    3. Neustarts/Aufwachen des Rechners der letzten 14 Tage (siehe auch
       ausfall_spurensuche.ps1, hier aber ueber einen laengeren Zeitraum, um
       ein Muster statt eines Einzelfalls zu sehen).
    4. Geplante Aufgaben mit einem Tages- oder Mehrtages-Trigger (ein
       Windows-Update-Neustart oder eine Wartungsaufgabe kann fuer genau so
       ein Muster sorgen).
    5. Energieverwaltung der Netzwerkkarte - darf Windows sie abschalten?
    6. Die eigenen "Verbindung verloren"-Zeilen aus dem Agent-Protokoll,
       gruppiert nach Tag - der lokale Abdruck desselben Musters, das schon
       in der Datenbank auffiel.

  Aendert NICHTS. Am besten ALS ADMINISTRATOR ausfuehren, sonst bleiben
  DHCP-Ereignisprotokoll und Aufgabenplanung teilweise unlesbar.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\liftpic\liftpic-sync\scripts\netz_muster_suche.ps1
#>
param(
  [string]$InstallDir = "C:\liftpic\liftpic-sync",
  [int]   $TageZurueck = 14
)

$ErrorActionPreference = "Continue"
$seit = (Get-Date).AddDays(-$TageZurueck)

function Kopf($text) {
  Write-Output ""
  Write-Output ("=" * 70)
  Write-Output ("  " + $text)
  Write-Output ("=" * 70)
}

Write-Output ""
Write-Output "Netz-Muster-Suche"
Write-Output ("Rechner   : " + $env:COMPUTERNAME)
Write-Output ("Zeitraum  : " + $seit.ToString("dd.MM.yyyy") + " bis jetzt")
Write-Output ("Jetzt     : " + (Get-Date).ToString("dd.MM.yyyy HH:mm:ss"))

$erhoeht = ([Security.Principal.WindowsPrincipal] `
  [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $erhoeht) {
  Write-Output ""
  Write-Output "  WARNUNG: nicht als Administrator gestartet - DHCP- und"
  Write-Output "  Aufgabenplanungs-Ereignisse bleiben dann wahrscheinlich leer."
}

# ---------------------------------------------------------------------------
Kopf "1. Aktuelle DHCP-Lease"
try {
  $adapter = Get-NetIPConfiguration -ErrorAction Stop | Where-Object { $_.IPv4Address }
  foreach ($a in $adapter) {
    $lease = Get-NetIPAddress -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
    Write-Output ("  Adapter: " + $a.InterfaceAlias + "  IP: " + $a.IPv4Address.IPAddress)
  }
  # Get-NetIPConfiguration liefert keine Lease-Zeiten direkt - ipconfig /all schon.
  $ipconfig = ipconfig /all 2>$null
  $block = $false
  foreach ($zeile in $ipconfig) {
    if ($zeile -match "Ethernet-Adapter|WLAN-Adapter|Ethernet adapter|Wireless LAN adapter") { $block = $true }
    if ($block -and ($zeile -match "Lease (Obtained|Erhalten)|Lease (Expires|Läuft ab)|IPv4-Adresse|IPv4 Address")) {
      Write-Output ("  " + $zeile.Trim())
    }
  }
} catch {
  Write-Output ("  nicht lesbar: " + $_.Exception.Message)
}

# ---------------------------------------------------------------------------
Kopf "2. DHCP-Erneuerungen der letzten $TageZurueck Tage - der tatsaechliche Takt"
# 50036 = Lease erneuert, 50037 = Lease abgelaufen/verloren, beide zeigen den
# echten Rhythmus, nicht nur die aktuell gueltige Lease.
try {
  $dhcp = Get-WinEvent -FilterHashtable @{
    LogName = "Microsoft-Windows-Dhcp-Client/Operational"
    Id = 50036, 50037, 50067, 50068
    StartTime = $seit
  } -ErrorAction Stop | Sort-Object TimeCreated

  if ($dhcp) {
    $vorher = $null
    foreach ($e in $dhcp) {
      $abstand = ""
      if ($vorher) {
        $diff = $e.TimeCreated - $vorher
        $abstand = ("  (Abstand zum vorigen: " + [math]::Round($diff.TotalHours, 1) + " h)")
      }
      Write-Output ("  " + $e.TimeCreated.ToString("dd.MM.yyyy HH:mm:ss") + "  [" + $e.Id + "]" + $abstand)
      $vorher = $e.TimeCreated
    }
    Write-Output ""
    Write-Output "  Wiederholt sich ein Abstand (z. B. immer ~48 h) -> das ist der Takt."
  } else {
    Write-Output "  Keine DHCP-Ereignisse in diesem Zeitraum - entweder feste IP,"
    Write-Output "  oder das Protokoll ist nicht aktiviert (dann unten Punkt 6 pruefen)."
  }
} catch {
  if ($_.Exception.Message -match "No events were found|keine Ereignisse gefunden") {
    Write-Output "  Keine DHCP-Ereignisse in diesem Zeitraum."
  } else {
    Write-Output ("  nicht lesbar: " + $_.Exception.Message)
    Write-Output "  (Dieses Protokoll ist auf manchen Rechnern nicht aktiviert. Aktivieren mit:"
    Write-Output "   wevtutil sl Microsoft-Windows-Dhcp-Client/Operational /e:true )"
  }
}

# ---------------------------------------------------------------------------
Kopf "3. Neustarts/Aufwachen der letzten $TageZurueck Tage"
try {
  $reboots = Get-WinEvent -FilterHashtable @{
    LogName = "System"; Id = 1,41,42,107,1074,6005,6006,6008; StartTime = $seit
  } -ErrorAction Stop | Sort-Object TimeCreated
  if ($reboots) {
    foreach ($e in $reboots) {
      $txt = ($e.Message -split "`r?`n")[0]
      if ($txt.Length -gt 100) { $txt = $txt.Substring(0, 100) + "..." }
      Write-Output ("  " + $e.TimeCreated.ToString("dd.MM.yyyy HH:mm:ss") + "  [" + $e.Id + "]  " + $txt)
    }
  } else {
    Write-Output "  Keine Neustarts, kein Aufwachen aus Standby in diesem Zeitraum."
  }
} catch {
  if ($_.Exception.Message -match "No events were found|keine Ereignisse gefunden") {
    Write-Output "  Keine Neustarts, kein Aufwachen aus Standby in diesem Zeitraum."
  } else {
    Write-Output ("  nicht lesbar: " + $_.Exception.Message)
  }
}

# ---------------------------------------------------------------------------
Kopf "4. Geplante Aufgaben mit taeglichem oder mehrtaegigem Trigger"
# Windows Update haengt seinen Neustart oft als eigene Aufgabe ein
# (UpdateOrchestrator) - die faellt hier mit auf.
try {
  $aufgaben = Get-ScheduledTask -ErrorAction Stop | Where-Object { $_.State -ne "Disabled" }
  foreach ($t in $aufgaben) {
    foreach ($trig in $t.Triggers) {
      if ($trig.CimClass.CimClassName -match "Daily|TimeTrigger") {
        $intervall = $trig.DaysInterval
        $zeile = "  " + $t.TaskPath + $t.TaskName
        if ($intervall) { $zeile += ("  (alle " + $intervall + " Tage)") }
        if ($trig.StartBoundary) { $zeile += ("  ab " + $trig.StartBoundary) }
        Write-Output $zeile
      }
    }
  }
} catch {
  Write-Output ("  nicht lesbar: " + $_.Exception.Message)
}
Write-Output ""
Write-Output "  Besonders WICHTIG: jede Aufgabe mit '(alle 2 Tage)' oder aehnlich oben,"
Write-Output "  und alles mit 'UpdateOrchestrator' oder 'Reboot' im Namen."

# ---------------------------------------------------------------------------
Kopf "5. Darf Windows die Netzwerkkarte abschalten?"
$strom = Get-CimInstance -ClassName MSPower_DeviceEnable -Namespace root\wmi -ErrorAction SilentlyContinue
$netzkarten = Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq "Up" }
foreach ($n in $netzkarten) {
  $eintrag = $strom | Where-Object { $_.InstanceName -like ("*" + $n.PnPDeviceID.Replace("\", "\\") + "*") }
  $stromSpar = if ($eintrag) { $eintrag.Enable } else { "unbekannt" }
  Write-Output ("  " + $n.Name + " (" + $n.InterfaceDescription + ")")
  Write-Output ("      Darf Windows abschalten um Strom zu sparen: " + $stromSpar)
}
Write-Output ""
Write-Output "  Steht hier 'True': das ist ein bekannter Grund fuer genau so ein"
Write-Output "  Muster - abschalten unter 'Geraete-Manager -> Netzwerkkarte ->"
Write-Output "  Energieverwaltung -> Der Computer kann das Geraet ausschalten...' entfernen."

# ---------------------------------------------------------------------------
Kopf "6. Eigene 'Verbindung verloren'-Zeilen, nach Tag gruppiert"
$logs = @()
foreach ($ort in @("$InstallDir\logs", "$InstallDir", "C:\liftpic\logs")) {
  if (Test-Path $ort) { $logs += Get-ChildItem $ort -Filter "*.log" -File -ErrorAction SilentlyContinue }
}
$logs = $logs | Sort-Object LastWriteTime -Descending | Select-Object -First 5
if (-not $logs) {
  Write-Output "  Kein Protokoll gefunden."
} else {
  $treffer = @{}
  $muster = "Verbindung.*verloren|network error|urlopen error|Ftp error|Remotename konnte nicht aufgel"
  foreach ($log in $logs) {
    $leser = [System.IO.File]::Open($log.FullName, "Open", "Read", "ReadWrite")
    $sr = New-Object System.IO.StreamReader($leser)
    while (-not $sr.EndOfStream) {
      $zeile = $sr.ReadLine()
      if ($zeile -match $muster -and $zeile -match "(\d{4}-\d{2}-\d{2})") {
        $tag = $matches[1]
        if (-not $treffer.ContainsKey($tag)) { $treffer[$tag] = 0 }
        $treffer[$tag] += 1
      }
    }
    $sr.Close(); $leser.Close()
  }
  if ($treffer.Count -eq 0) {
    Write-Output "  Keine passenden Zeilen in den letzten 5 Protokolldateien."
  } else {
    foreach ($tag in ($treffer.Keys | Sort-Object)) {
      Write-Output ("  " + $tag + "  " + $treffer[$tag] + " Treffer")
    }
  }
}

# ---------------------------------------------------------------------------
Kopf "Fertig - so liest man das Ergebnis"
Write-Output "  Punkt 2 zeigt einen wiederkehrenden Abstand   -> DHCP/Router ist der Takt."
Write-Output "  Punkt 3 zeigt Neustarts im selben Rhythmus    -> der PC selbst startet neu."
Write-Output "  Punkt 4 zeigt eine '(alle 2 Tage)'-Aufgabe    -> das ist wahrscheinlich der Taeter."
Write-Output "  Punkt 5 zeigt 'True'                          -> Energieverwaltung, unabhaengig vom Rhythmus."
Write-Output "  Punkt 6 zeigt denselben Rhythmus lokal        -> bestaetigt, dass es kein DB-Zufall ist."
Write-Output ""
Write-Output "Fuer einen einzelnen Zeitpunkt danach (z.B. den naechsten Ausfall):"
Write-Output "  .\ausfall_spurensuche.ps1 -Ausfall '<Datum Uhrzeit>'"
Write-Output ""
Write-Output "Ausgabe bitte komplett kopieren und weitergeben."
Write-Output ""
