# Windows Install, Upgrade, Rollback

## Install prerequisites

- Windows 10/11
- Internet access
- Administrator rights on the attraction PC

The normal install no longer needs Git or manual Supabase `.env` editing. The
bootstrap installer checks Python and tries to install Python 3.12 with winget
if it is missing.

## Simple one-file install

Use this for a normal customer/attraction PC.

1. In the Staff Dashboard open `Kunden Management -> Liftpic PCs`.
2. Create or edit the Liftpic PC.
3. For a running attraction, keep `Shadow Mode` enabled first.
4. Download `install_liftpic_sync_bootstrap.ps1`.
5. Save it on the attraction PC, normally in `Downloads`.
6. Copy the PC row's install command from the dashboard and run it in an
   Administrator PowerShell.

The command looks like this:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\install_liftpic_sync_bootstrap.ps1" -PairingCode YOURCODE
```

The installer:

- downloads the latest code from GitHub
- copies it to `C:\liftpic\liftpic-sync`
- creates `C:\liftpic\liftpic-sync\.env` with the Supabase project URL
- pairs the PC with the dashboard using `YOURCODE`
- watches common old Liftpic log folders read-only for system health signals
- installs a scheduled task named `LiftpicSync`
- starts the sync in the background

## Safe install on a running attraction

Yes, the new sync can be installed while the old attraction software is still
running, if `Shadow Mode` stays enabled.

In shadow mode:

- TIScapture/CAM keeps writing to `C:\liftpic\fotos`
- AidaTest keeps writing to `C:\liftpic\fotos\out`
- PhotoViewer/print keeps running normally
- Liftpic Sync reads folders and writes only its SQLite/log state
- no old Liftpic program is stopped
- no local image is deleted
- local print/logo asset sync stays off unless `ASSET_SYNC_ENABLED=true`
- coin/terminal/printer/camera health is detected only from local log files;
  the sync does not control payment hardware

Do not run the old uploader and the new uploader live against the same sold
photos at the same time. First observe in shadow mode, check health/ride counts,
then either stop the old uploader or keep Liftpic Sync in count-only mode.

## Install from source

```powershell
cd C:\liftpic
git clone https://github.com/john123-05/testsoftware.git liftpic-sync
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
