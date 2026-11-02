param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9-]{36}$')][string]$InstallationId)
$ErrorActionPreference='Stop'
$dir='C:\liftpic\liftpic-sync'
if(-not(Test-Path "$dir\.env")){throw 'Zuerst den Agenten installieren.'}
$python=if(Test-Path "$dir\.venv\Scripts\python.exe"){"$dir\.venv\Scripts\python.exe"}else{(Get-Command python.exe -ErrorAction Stop).Source}
Push-Location "$dir\src"
try{& $python -m liftpic_sync.assistant_test --installation-id $InstallationId --install-dir $dir;if($LASTEXITCODE -ne 0){throw 'Testfoto nicht vollstaendig bestaetigt. CRM offen lassen.'}}finally{Pop-Location}
