<# Read-only PC inventory. Writes ONLY the two reports; never exports secrets or whole configs. #>
param(
  [string[]]$Roots = @('C:\liftpic'),
  [string]$OutputDir = (Join-Path $env:USERPROFILE 'Downloads'),
  [string]$InstallationId = ''
)
$ErrorActionPreference = 'Stop'
$allowedTags = @('CustomerNumber','CustomerNumberPositions','CodePositions','CodePositionsInFilename',
  'CustomerNumber2','CodePositionsInFilename2','CustomerNumber3','CodePositionsInFilename3',
  'QrCodeBeginningString','PricePrint','PriceEmail','PriceFacebook','PricePrintWithQrCode',
  'PricePrintWithoutQrCode','PriceQrCodeShare','EnablePrint','EnableEmail','EnableCreditCardPayment',
  'EnableQrCodePrintButtons','EnableQrCodeShare','Currency','ImageDirectory','InputDirectory','OutputDirectory')
$allowedEnv = @('RAW_DIR','PROCESSED_DIR','QRCODE_DIR','QRCODE_DIR_2','WEBOUT_DIR','STATISTIC_FILE',
 'PRINT_COUNT_FILE','VIEWER_SETTINGS_XML','SPEED_LOG_FILE','COIN_STATS_FILE','COIN_LOG_GLOB','CARD_LOG_GLOB',
 'CUSTOMER_CODE','CAMERA_CODE','MACHINE_ID','PARK_ID','UPLOAD_SOURCE','FILE_CODE_POSITIONS','RIDE_COUNT_PARITY','SHADOW_MODE')
function Get-Hash([byte[]]$Bytes) {
 $sha = [Security.Cryptography.SHA256]::Create()
 try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
}
function Read-Viewer([string]$Path) {
 if ((Get-Item -LiteralPath $Path).Length -gt 2097152) { return $null }
 $bytes = [IO.File]::ReadAllBytes($Path)
 $text = [Text.Encoding]::UTF8.GetString($bytes)
 if ($text.Contains([char]0xFFFD)) { $text = [Text.Encoding]::GetEncoding(28591).GetString($bytes) }
 $fields = [ordered]@{}
 foreach ($tag in $allowedTags) {
  $m = [regex]::Match($text, '<' + $tag + '>\s*([^<]{0,500})\s*</' + $tag + '>', 'IgnoreCase')
  if ($m.Success) { $fields[$tag] = [Net.WebUtility]::HtmlDecode($m.Groups[1].Value.Trim()) }
 }
 return [ordered]@{ settings_path=$Path; sha256=(Get-Hash $bytes); fields=$fields }
}
$warnings = New-Object 'System.Collections.Generic.List[string]'
$programs = @()
try {
 $programs = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
  $_.Name -match '^(PhotoViewerFacebook|3gerTis|TIScapture|camera26|AidaTest|Speedshot|jpeg4web).*\.exe$'
 } | Select-Object -First 20 | ForEach-Object { [ordered]@{name=$_.Name;path=[string]$_.ExecutablePath} })
} catch { $warnings.Add('Laufende Programme nicht lesbar; bei Bedarf mit Administratorrechten wiederholen.') }
$search = @($Roots | Select-Object -Unique)
foreach ($p in $programs) { if ($p.path) { $search += Split-Path -Parent $p.path } }
$settingsFiles = @()
$pathCandidates = [ordered]@{}
$environment = [ordered]@{}
foreach ($root in @($search | Select-Object -Unique | Select-Object -First 10)) {
 if (-not (Test-Path -LiteralPath $root -PathType Container)) { $warnings.Add("Suchordner fehlt: $root"); continue }
 # Bounded depth, file names and count; do not walk photo collections recursively.
 $dirs = @((Get-Item -LiteralPath $root)) + @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -notmatch '^(fotos|photos|backups|state|logs|\.venv|node_modules)$' } | Select-Object -First 40)
 foreach ($dir in $dirs) {
  $candidate = Join-Path $dir.FullName 'Settings.xml'
  if (Test-Path -LiteralPath $candidate -PathType Leaf) {
   $settingsFiles += $candidate
   foreach ($name in @('Statistic.txt','PrintCount.txt','CoinStats.txt')) { $local=Join-Path $dir.FullName $name; if(Test-Path -LiteralPath $local) {$pathCandidates[$local]=$true} }
  }
 }
 foreach ($rel in @('fotos','fotos\out','fotos\qrcode','fotos\qrcode2','fotos\webout','samuel_neu\Statistic.txt','samuel_neu\PrintCount.txt')) {
  $path = Join-Path $root $rel
  if (Test-Path -LiteralPath $path) { $pathCandidates[$path] = $true }
 }
 $envFile = Join-Path $root 'liftpic-sync\.env'
 if ((Test-Path -LiteralPath $envFile -PathType Leaf) -and (Get-Item -LiteralPath $envFile).Length -lt 65536) {
  foreach ($line in [IO.File]::ReadAllLines($envFile)) {
   if ($line -match '^\s*([A-Z_0-9]+)\s*=(.{0,500})$' -and $allowedEnv -contains $Matches[1]) {
    $environment[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
   }
  }
 }
 foreach ($ini in @('kosel\AidaTest.ini','3GerTis\Speedshot.ini','speedshot\Speedshot.ini','jpeg4web\jpeg4web.ini')) {
  $file = Join-Path $root $ini
  if ((Test-Path -LiteralPath $file -PathType Leaf) -and (Get-Item -LiteralPath $file).Length -lt 65536) {
   foreach ($line in [IO.File]::ReadAllLines($file)) {
    if ($line -match '^\s*(InputDir|OutputDir|original_folder|Filename)\s*=\s*([A-Za-z]:\\.{1,450})$') {
     $pathCandidates[$Matches[2].Trim()] = (Test-Path -LiteralPath $Matches[2].Trim())
    }
   }
  }
 }
}
if ($environment.Contains('VIEWER_SETTINGS_XML') -and (Test-Path -LiteralPath $environment['VIEWER_SETTINGS_XML'])) { $settingsFiles += $environment['VIEWER_SETTINGS_XML'] }
$viewers = @()
foreach ($file in @($settingsFiles | Select-Object -Unique | Select-Object -First 10)) {
 try { $v = Read-Viewer $file; if ($v) { $viewers += $v } } catch { $warnings.Add("Settings.xml nicht lesbar: $file") }
}
$tasks = @()
try { $tasks = @(Get-ScheduledTask -ErrorAction Stop | Where-Object {$_.TaskName -in @('LiftpicSync','LiftpicSyncWatchdog')} | ForEach-Object {
 [ordered]@{name=$_.TaskName;state=[string]$_.State}
}) } catch { $warnings.Add('Aufgabenplanung nicht lesbar.') }
foreach ($key in $allowedEnv) {
 if ($environment.Contains($key) -and $key -match '(_DIR|_FILE|_XML)$') { $pathCandidates[$environment[$key]] = (Test-Path -LiteralPath $environment[$key]) }
}
$report = [ordered]@{
 schema_version=1; created_at=[DateTime]::UtcNow.ToString('o'); scan_id=[guid]::NewGuid().ToString(); installation_id=$InstallationId
 viewers=$viewers; environment=$environment; programs=$programs; tasks=$tasks
 paths=@($pathCandidates.Keys | Select-Object -First 80 | ForEach-Object { [ordered]@{path=$_;exists=[bool]$pathCandidates[$_]} })
 warnings=@($warnings | Select-Object -First 30)
}
if (-not (Test-Path -LiteralPath $OutputDir -PathType Container)) { throw 'Ausgabeordner fehlt. Bitte -OutputDir auf einen vorhandenen Ordner setzen.' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$jsonPath = Join-Path $OutputDir "Liftpictures-PC-$stamp.json"
$txtPath = Join-Path $OutputDir "Liftpictures-PC-$stamp.txt"
$json = $report | ConvertTo-Json -Depth 8
if ([Text.Encoding]::UTF8.GetByteCount($json) -gt 60000) { throw 'Bericht zu gross; Suchorte eingrenzen.' }
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($jsonPath,$json,$utf8)
[IO.File]::WriteAllText($txtPath,"Liftpictures PC-Auslesebericht (nur erlaubte Felder; kein Konfigurationsexport)`r`n$json",$utf8)
Write-Host "Nur gelesen. Bitte diese Datei im Chat oder CRM hochladen: $jsonPath"
Write-Host "Textfassung: $txtPath"
