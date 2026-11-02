# Used only by the assistant installer; existing installations keep their old watchdog.
$ErrorActionPreference='Stop'
$dir='C:\liftpic\liftpic-sync'
$watchdog=Join-Path $dir 'assistant-watchdog-run.ps1'
$body=@'
$ErrorActionPreference='Stop'
$dir='C:\liftpic\liftpic-sync'
if (Test-Path "$dir\paused") { exit 0 }
$lock=$null
try { $lock=[IO.File]::Open("$dir\.installation.lock",[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) } catch { exit 0 }
try {
 $running=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*liftpic_sync.cli run*' -and $_.CommandLine.Contains("$dir\.env") })
 if (-not $running.Count) { if(Get-Service LiftpicSync -ErrorAction SilentlyContinue){Start-Service LiftpicSync}else{Start-ScheduledTask -TaskName LiftpicSync} }
} finally { $lock.Dispose() }
'@
Set-Content -LiteralPath $watchdog -Value $body -Encoding ASCII
$a=New-ScheduledTaskAction -Execute powershell.exe -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchdog`""
$t=New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
$s=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName LiftpicSyncWatchdog -Action $a -Trigger $t -Settings $s -User SYSTEM -RunLevel Highest -Force | Out-Null
