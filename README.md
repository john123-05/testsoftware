# Liftpic Sync

Liftpic Sync is the new shared software base for Liftpictures photo systems.
It watches local attraction photo folders, matches speed data, keeps a durable
SQLite upload queue, and uploads photos plus metadata through a Supabase API.

This repository is intentionally generic. Each attraction/client PC should use
the same code. The preferred setup is now: create the PC/camera in the Staff
Dashboard Liftpic Setup page, copy the pairing code, and let `liftpic-sync`
fill local park, camera, folder and token settings.

## Why this exists

The current PCs have several older programs chained together:

- camera/capture software writes raw images into `C:\liftpic\fotos`
- `AidaTest`/Speedshot creates processed speed images in `C:\liftpic\fotos\out`
- `PhotoViewerFacebook` copies sold photos into `C:\liftpic\fotos\qrcode`
- Liftpic Sync renames sold photos from `qrcode` into `webout` and uploads them
- Liftpic Sync counts every ride from `fotos/out` and `fotos` as small
  telemetry, so dashboards can show rides vs. sold photos without uploading
  every unsold JPEG
- optionally, Liftpic Sync can pull dashboard-managed local assets such as
  Verkaufsautomat logos and print overlays back down to the PC
- a small Python uploader uploads a watched folder directly to Supabase Storage

That works, but it is hard to reason about, hard to reinstall on a different
PC, and fragile during restarts/network outages. Liftpic Sync moves the fragile
parts into one versioned service.

## First install on a Windows attraction PC

Normal install is now one PowerShell file:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\install_liftpic_sync_bootstrap.ps1" -PairingCode YOURCODE
```

`YOURCODE` comes from `Kunden Management -> Liftpic PCs` in the Staff Dashboard.
The installer downloads this repository, installs it to
`C:\liftpic\liftpic-sync`, creates `.env`, pairs the PC, and starts the
scheduled task `LiftpicSync`.

Manual/source install is documented in `docs/INSTALL_WINDOWS.md`.

For development:

```powershell
python -m pip install -e .[dev]
python -m liftpic_sync.cli --env .env scan-once
python -m pytest
```

## Safe rollout

Use `SHADOW_MODE=true` first. In shadow mode Liftpic Sync scans, queues and logs
events, but it does not upload or modify existing Liftpic folders.

Ride counting is safe in shadow mode too: it writes only to the local SQLite
state database and logs the heartbeat payload. Unbought photos are never sent
as image files just to calculate conversion.

Local asset sync is disabled by default. See `docs/ASSET_SYNC.md` before
enabling it because it replaces local logo/overlay files, with backups.

The first live rollout should use a test Supabase project/bucket before
production. Do not disable the old system until `qrcode -> webout -> upload`
and the queue status are verified.

## GitHub workflow

The repository contains CI tests and a Windows EXE build workflow. Releases can
be installed on other PCs without copying random scripts by hand.

Never commit `.env`, Supabase service role keys, device tokens, or customer
secrets.
