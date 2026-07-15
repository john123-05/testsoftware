# Agent Handoff Notes

This file is for Codex, other LLM agents, and future maintainers.

## Current mission

Build a reliable repo-based replacement for the ad hoc Liftpictures uploader
setup. The service must run across many attraction PCs with the same code and
different park/machine configuration.

## Current PC findings from 2026-07-14

- Workspace: `C:\Users\Nolting\Downloads\Cursor Software`
- Existing local copy: `uploader\`
- Production-like folder: `C:\liftpic\uploader`
- Git was not available in PATH during initial inspection.
- Python 3.14.6 was available.
- Node, Deno and Supabase CLI were not available in PATH.
- `TIScapture` stores raw photos in `C:\liftpic\fotos`.
- `AidaTest.exe` was observed running from `C:\liftpic\kosel\AidaTest.exe`.
- `AidaTest.ini` uses:
  - `InputDir=c:\liftpic\fotos\`
  - `OutputDir=c:\liftpic\fotos\out\`
  - `SaveInfoToImageFilename=1`
  - `ShowSpeed=1`
- `C:\liftpic\fotos\out` contains processed names like
  `00046_202607141349431395.jpg`.
- `C:\liftpic\fotos\webout` was empty during inspection.
- `jpeg4web.ini` was configured as `qrcode -> webout` and `original_folder=out`.
- User's father clarified the intended sold-photo flow:
  `PhotoViewerFacebook -> C:\liftpic\fotos\qrcode`, then new software renames
  those sold files into `C:\liftpic\fotos\webout` and uploads webout.
- Filename formula uses `N` customer/internal code, `T` date code and `Z` camera
  picture number without the first digit.
- `C:\liftpic\samuel_neu\PrintCount.txt` was observed with value `237`.
- Startup included `C:\liftpic\del_pic.bat`, which deletes local JPG queues.

## Overlay/asset findings from 2026-07-15

- Active viewer config is `C:\liftpic\samuel_neu\Settings.xml`.
- Important local viewer/print targets found:
  - `C:\liftpic\samuel_neu\diabolos.png` for viewer logo/preview references.
  - `C:\liftpic\samuel_neu\preview_logo3.png` for default/start photo.
  - `C:\liftpic\samuel_neu\image1.png` for `SinglePhotoLogoFilename` and
    `OverlayImageFilename`.
  - `C:\liftpic\samuel_neu\overlay.png`, `hintergrund.png`, styles folders.
  - `C:\liftpic\imageloader\Vorlage5.bmp` and `vorlage4.bmp` for old print
    templates.
  - `C:\liftpic\jpeg4web\fiebich.png` from old `jpeg4web.ini`.
- The new asset downsync intentionally does not edit `Settings.xml`; it replaces
  only approved target files and keeps backups under
  `C:\liftpic\liftpic-sync\backups\assets`.

## Remote state from 2026-07-15

- Supabase project used for Liftpic staff/backend work:
  `kvpcwlcfgmsmarjtwpsx`.
- Edge Functions deployed:
  - `liftpic-assets`
  - `admin-liftpic-assets` from dashboard2
- SQL applied remotely through `supabase db query --linked`:
  - `0001_liftpic_sync.sql`
  - `0002_liftpic_machine_configs.sql`
  - `0003_liftpic_asset_deployments.sql`
- Verification query confirmed:
  `liftpic_machine_configs`, `liftpic_asset_deployments`, and private storage
  bucket `liftpic-assets` exist.

## Safety rules

- Do not commit `.env`, service role keys, device tokens, customer passwords, or
  Supabase secrets.
- Do not delete or rewrite live `C:\liftpic\fotos` images while developing.
- Keep new software under `C:\liftpic\liftpic-sync` unless the user explicitly
  asks otherwise.
- Prefer shadow mode on first rollout.
- Legacy scripts may be kept in `legacy/` for reference only.

## Implementation notes

- The Python service has no runtime dependencies outside the standard library.
- Local durability is SQLite, not JSON-only state.
- Supabase writes go through Edge Functions and signed upload URLs. The PC
  should not need a Supabase service role key.
- Ride counting is separate from photo upload. `RideTracker` scans
  `fotos\out`/`fotos`, stores de-duplicated ride events in SQLite, and sends
  daily counters through `liftpic-status`. Only sold QR-code images from
  `fotos\qrcode` are staged/uploaded as JPEGs.
- Staff Dashboard owns the intended config UI. New PCs should be created in
  Liftpic Setup, then paired locally with `liftpic-sync pair --code ...`.
  The pairing endpoint returns only machine config and that machine's device
  token; service role keys must never be placed on the PC.
- Normal customer PC install should use
  `scripts/install_liftpic_sync_bootstrap.ps1`, downloaded from the Staff
  Dashboard. It installs to `C:\liftpic\liftpic-sync`, creates `.env` with
  public Supabase URL/anon key, asks for or accepts a pairing code, then starts
  the scheduled task `LiftpicSync`.
- Local logos/overlays are now controlled through dashboard2's Liftpic PCs tab.
  The dashboard uploads assets to the private `liftpic-assets` bucket and writes
  `liftpic_asset_deployments`. The PC polls `liftpic-assets`, downloads signed
  files, validates SHA256 when present, backs up the old local file, then
  atomically replaces the target.
- Do not key photo events only by `capture_id`: the camera counter resets
  nightly. Use `event_key = MACHINE_ID + CAMERA_CODE + business date +
  capture_id` for both ride events and sold-photo upload events.
- If GitHub push fails because Git/auth is missing, finish the local repo and
  report the exact next command once credentials are available.
