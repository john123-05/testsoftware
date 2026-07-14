$ErrorActionPreference = "Stop"
$serviceName = "LiftpicSync"

if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
  Restart-Service -Name $serviceName
  Write-Host "Restarted service $serviceName"
} elseif (Get-ScheduledTask -TaskName $serviceName -ErrorAction SilentlyContinue) {
  Stop-ScheduledTask -TaskName $serviceName -ErrorAction SilentlyContinue
  Start-ScheduledTask -TaskName $serviceName
  Write-Host "Restarted scheduled task $serviceName"
} else {
  Write-Warning "No LiftpicSync service or scheduled task found"
}
