# Liftpic Sync

Liftpic Sync is the new shared software base for Liftpictures photo systems.
It watches local attraction photo folders, matches speed data, keeps a durable
SQLite upload queue, and uploads photos plus metadata through a Supabase API.

This repository is intentionally generic. Each attraction/client PC should use
the same code and only change local configuration such as `PARK_SLUG`,
`PARK_ID`, `CUSTOMER_CODE`, `MACHINE_ID`, folder paths, and `DEVICE_TOKEN`.

## Why this exists

The current PCs have several older programs chained together:

- camera/capture software writes raw images into `C:\liftpic\fotos`
- `AidaTest`/Speedshot creates processed speed images in `C:\liftpic\fotos\out`
- `PhotoViewerFacebook` copies sold photos into `C:\liftpic\fotos\qrcode`
- Liftpic Sync renames sold photos from `qrcode` into `webout` and uploads them
- a small Python uploader uploads a watched folder directly to Supabase Storage

That works, but it is hard to reason about, hard to reinstall on a different
PC, and fragile during restarts/network outages. Liftpic Sync moves the fragile
parts into one versioned service.

## First install on a Windows attraction PC

1. Install Python 3.11 or newer.
2. Clone or download this repository.
3. Install to `C:\liftpic\liftpic-sync`.
4. Copy `config\park.example.env` to `.env`.
5. Edit only attraction-specific values.
6. Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_service.ps1
```

For development:

```powershell
python -m pip install -e .[dev]
python -m liftpic_sync.cli --env .env scan-once
python -m pytest
```

## Safe rollout

Use `SHADOW_MODE=true` first. In shadow mode Liftpic Sync scans, queues and logs
events, but it does not upload or modify existing Liftpic folders.

The first live rollout should use a test Supabase project/bucket before
production. Do not disable the old system until `qrcode -> webout -> upload`
and the queue status are verified.

## GitHub workflow

The repository contains CI tests and a Windows EXE build workflow. Releases can
be installed on other PCs without copying random scripts by hand.

Never commit `.env`, Supabase service role keys, device tokens, or customer
secrets.
