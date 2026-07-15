# Windows Install, Upgrade, Rollback

## Install prerequisites

- Windows 10/11
- Python 3.11 or newer, or a released `liftpic-sync.exe`
- Git for Windows if installing from source

## Install from source

```powershell
cd C:\liftpic
git clone https://github.com/tomnotes2/testsoftware.git liftpic-sync
cd C:\liftpic\liftpic-sync
python -m pip install -e .
copy config\park.example.env .env
notepad .env
python -m liftpic_sync.cli --env .env pair --code YOURCODE
powershell -ExecutionPolicy Bypass -File scripts\install_windows_service.ps1
```

`YOURCODE` comes from the Staff Dashboard under Liftpic Setup. On a normal new
PC, only `SUPABASE_FUNCTIONS_URL`, `SUPABASE_URL`, and `SUPABASE_ANON_KEY` have
to be entered before pairing. Park, camera, customer code, folder paths and
device token are written by the pairing command.

## Run once for testing

```powershell
python -m liftpic_sync.cli --env .env scan-once
python -m liftpic_sync.cli --env .env health
```

## Install as Windows service

The script uses `nssm.exe` as a real Windows service wrapper if it is installed.
If NSSM is not available, it creates a scheduled task fallback.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_service.ps1
```

## Upgrade

```powershell
cd C:\liftpic\liftpic-sync
git pull
python -m pip install -e .
powershell -ExecutionPolicy Bypass -File scripts\restart_service.ps1
```

## Rollback

```powershell
cd C:\liftpic\liftpic-sync
git tag
git checkout <previous-tag>
python -m pip install -e .
powershell -ExecutionPolicy Bypass -File scripts\restart_service.ps1
```

If Git is not available, replace the folder with the previous release archive
and run the install script again.

## Verify

```powershell
powershell -ExecutionPolicy Bypass -File scripts\healthcheck.ps1
```

Look for:

- SQLite database exists
- logs are being written
- queue count is not growing forever
- Supabase API returns success in live mode
