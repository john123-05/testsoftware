<#
.SYNOPSIS
  Bilder vom Automaten fuer die Personalisierungs-Seite einsammeln.
.DESCRIPTION
  Die Personalisierung im Dashboard hat drei Plaetze (siehe dashboard2
  operator-liftpic-assets): Foto-Overlay (samuel_neu\overlay.png), Automat-Logo
  (samuel_neu\diabolos.png) und Hintergrund (samuel_neu\hintergrund.png). Damit
  dort von Anfang an "so ist es gerade am Automaten" steht, sammelt dieses Skript
  diese Dateien, alle in der Settings.xml genannten Bilder und die Bilder aus den
  Programmordnern (Verkaufsprogramm, Druck, jpeg4web, Kamera) in eine ZIP im
  Downloads-Ordner. Die ZIP per AnyDesk auf den Mac ziehen; die Bilder werden dann
  auf der Personalisierungs-Seite als aktueller Stand hinterlegt.
  Es wird nichts veraendert, nur kopiert.
.EXAMPLE
  .\bilder_export.ps1 -Slug doberan
#>
param(
  [Parameter(Mandatory = $true)][string]$Slug,
  # Zielordner; ohne Angabe der Downloads-Ordner des Benutzers (setup.ps1 nimmt den oeffentlichen Desktop).
  [string]$Ziel = ""
)
$ErrorActionPreference = "Stop"
$out = if ($Ziel) { Join-Path $Ziel "$Slug-bilder" } else { Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads\$Slug-bilder" }
Remove-Item $out, "$out.zip" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $out | Out-Null

function Flach([string]$pfad) { ($pfad -replace '^[A-Za-z]:\\', '') -replace '\\', '__' }
$kopiert = @{}
function Kopiere([string]$quelle, [string]$praefix) {
  if ($kopiert.ContainsKey($quelle)) { return }
  Copy-Item $quelle (Join-Path $out "$praefix$(Flach $quelle)") -Force
  $kopiert[$quelle] = $true
}

# 1) Die drei Plaetze der Personalisierungs-Seite
$plaetze = [ordered]@{
  "1-FOTO-OVERLAY__"  = "C:\liftpic\samuel_neu\overlay.png"
  "1-AUTOMAT-LOGO__"  = "C:\liftpic\samuel_neu\diabolos.png"
  "1-HINTERGRUND__"   = "C:\liftpic\samuel_neu\hintergrund.png"
}
foreach ($p in $plaetze.Keys) { if (Test-Path $plaetze[$p]) { Kopiere $plaetze[$p] $p } }

# 2) Alle Bilder, die die Settings.xml nennt
$settings = "C:\liftpic\samuel_neu\Settings.xml"
$refs = @()
if (Test-Path $settings) {
  $refs = @(Select-String -Path $settings -Pattern '<(\w+)>([^<]+\.(png|jpg|jpeg|bmp|gif))</' -AllMatches |
    ForEach-Object { $_.Matches } |
    ForEach-Object { [pscustomobject]@{ Feld = $_.Groups[1].Value; Datei = $_.Groups[2].Value; Da = (Test-Path $_.Groups[2].Value) } })
  foreach ($r in $refs | Where-Object Da) { Kopiere $r.Datei "2-$($r.Feld)__" }
}

# 3) Bilder aus den Programmordnern (keine Kundenfotos)
$ordner = @(Get-ChildItem C:\liftpic -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match '^(samuel_neu$|imageloader|jpeg4web|3ger|speedshot|kosel)' } |
  ForEach-Object FullName)
foreach ($q in $ordner) {
  Get-ChildItem $q -Recurse -Depth 2 -File -Include *.png, *.jpg, *.jpeg, *.bmp, *.gif -ErrorAction SilentlyContinue |
    Where-Object { $_.Length -lt 20MB -and $_.FullName -notmatch '\\fotos\\' -and $_.Name -notmatch '^t?\d{4,}' } |
    ForEach-Object { Kopiere $_.FullName "3-" }
}

$bericht = & {
  "Bilder vom Automaten $Slug - $(Get-Date -Format 'dd.MM.yyyy HH:mm')"
  ""
  "Plaetze der Personalisierungs-Seite:"
  foreach ($p in $plaetze.Keys) { "  $($p.Trim('_'))  $($plaetze[$p])  $(if (Test-Path $plaetze[$p]) { 'vorhanden' } else { 'fehlt' })" }
  ""
  "Bilder laut Settings.xml:"
  $refs | Format-Table -AutoSize | Out-String -Width 250
  "Durchsuchte Ordner:"
  $ordner | ForEach-Object { "  $_" }
}
$bericht | Out-File (Join-Path $out "0-uebersicht.txt") -Encoding utf8
Compress-Archive "$out\*" "$out.zip" -Force
$bericht | ForEach-Object { Write-Host $_ }
Write-Host "Bilder-Export: $out.zip ($($kopiert.Count) Bilder) - per AnyDesk auf den Mac ziehen." -ForegroundColor Green
