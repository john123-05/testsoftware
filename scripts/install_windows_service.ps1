param(
  [string]$InstallDir = "C:\liftpic\liftpic-sync",
  [string]$EnvFile = "C:\liftpic\liftpic-sync\.env"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $InstallDir)) {
  New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
}

$python = (Get-Command python -ErrorAction Stop).Source
$args = "-m liftpic_sync.cli --env `"$EnvFile`" run"
$serviceName = "LiftpicSync"

$nssm = Get-Command nssm.exe -ErrorAction SilentlyContinue
if ($nssm) {
  if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
    & $nssm.Source stop $serviceName | Out-Null
    & $nssm.Source remove $serviceName confirm | Out-Null
    Start-Sleep -Seconds 2
  }

  & $nssm.Source install $serviceName $python $args | Out-Null
  & $nssm.Source set $serviceName AppDirectory $InstallDir | Out-Null
  & $nssm.Source set $serviceName Start SERVICE_AUTO_START | Out-Null
  & $nssm.Source start $serviceName | Out-Null
  Write-Host "Installed NSSM Windows service $serviceName"
} else {
  Write-Warning "nssm.exe not found, creating scheduled task fallback"
  $action = New-ScheduledTaskAction -Execute $python -Argument $args -WorkingDirectory $InstallDir
  $trigger = New-ScheduledTaskTrigger -AtLogOn
  Register-ScheduledTask -TaskName $serviceName -Action $action -Trigger $trigger -Description "Liftpic Sync fallback task" -Force | Out-Null
  Start-ScheduledTask -TaskName $serviceName
  Write-Host "Installed scheduled task $serviceName"
}
