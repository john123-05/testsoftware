# Agent Handoff Notes

This file is for Codex, other LLM agents, and future maintainers.

**Start with `docs/ECOSYSTEM.md`** - it maps the whole Liftpictures
landscape (all repos, both Supabase projects, customers, the claim-code
incident history) so you have full context before touching anything.
`docs/PC_SETUP_CHECKLIST.md` holds Tom's field-install knowledge
(BIOS/AnyDesk/.NET/drivers/payment terminal) that this repo deliberately
does not automate.

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
- Operational health monitoring is read-only. `operational_monitor.py` tails
  configured `OPERATIONAL_LOG_GLOBS` and summarizes old logs into heartbeat
  fields: `operational_devices`, `operational_events`, `coin_status`,
  `terminal_status`, `printer_status`, and `camera_status`. It must not control
  COM ports, coin validators, ZVT terminals, printers, or cameras.
- Do not key photo events only by `capture_id`: the camera counter resets
  nightly. Use `event_key = MACHINE_ID + CAMERA_CODE + business date +
  capture_id` for both ride events and sold-photo upload events.
- If GitHub push fails because Git/auth is missing, finish the local repo and
  report the exact next command once credentials are available.

## Plose onboarding (2026-10-03) - new patterns for the next new customer

Plose (Plosebob summer toboggan, South Tyrol) was the first customer whose
on-site setup didn't fit any existing assumption. Three machine-level
settings got added, all opt-in (default = old behavior unchanged, so no
existing machine's `.env` is affected unless its dashboard config explicitly
sets them):

- **`UPLOAD_SOURCE=statistic`** (`mode='sold_via_statistic'` in
  `liftpic_machine_configs`) - for sale software with no qrcode staging step
  at all. Pressing "Kaufen" only appends a line to a `Statistic.txt`-style
  sale log (`DATE::C:\path\to\captured\file.jpg::code`); `scanner.py`'s
  `_statistic_sold_images()` reads that log instead of watching a folder, and
  resolves each sold filename back to its real file (preferring the
  processed/speed-stamped copy over the raw capture).
- **`QRCODE_DIR_2`** - for a machine with two independent camera PCs that
  each have their own "sold" folder (`qrcode`/`qrcode2`) instead of sharing
  one.
- **`settings.ride_count_parity`** (`"even"`/`"odd"`, default `"all"`) - for
  two cameras covering the SAME ride (one assigns even capture numbers, the
  other odd). Counting every capture as its own ride doubles the real total;
  this counts rides from only one camera's stream.

**A real, previously-undiscovered bug found and fixed along the way**:
`liftpic-ingest-commit`'s `writeClaimablePhoto()` only turns an upload into a
*correct* claimable `photos` row (real `speed_kmh`/`captured_at` from
`photo_events`) when the event's metadata has `sold_source_path` set -
normally true only for files pulled from the `qrcode` folder. Every other
upload still gets a `photos` row (a separate DB trigger on the raw storage
upload creates one), but that trigger has none of the rich metadata, so it
silently falls back to `speed_kmh=0`/`captured_at=upload time` - and nothing
ever corrects it afterward for a park with no qrcode step. **Any new
sold-photo detection mechanism you add must also set `sold_source_path` in
scanner.py's metadata**, or its uploads will look "sold" but carry wrong
speed/time data forever. (Plose had ~11 already-uploaded photos stuck this
way; fixed by hand via SQL after the code fix shipped - check for this class
of symptom - `speed_kmh = 0` instead of `null`, `captured_at` suspiciously
equal to `created_at` - on any new customer's first live day too.)

**Dashboard2 hardcoded per-park lists that silently fall back to Imst's look
when a new park isn't added** - grep for the new customer's old park_id
missing from these after onboarding, or things will look subtly wrong without
an obvious error:
- `src/lib/photoBrowser.ts` `CLAIM_BASE_BY_PARK` (no entry -> no "Claim-Link
  kopieren" button or QR code in the staff Foto-Browser).
- `src/lib/parkBrand.ts` `PARK_ACCENT_COLOR` (no entry -> CRM
  Umfrage/Social preview falls back to Imst gold). If the new park's brand
  color is dark, also check `accentTextColorForPark`'s contrast still reads
  right (it auto-computes light/dark text via YIQ, but verify).
- `src/components/GuestActivityAwareOverlay.tsx` and the matching check in
  `src/components/layout/Sidebar.tsx` (`isTarzansPark`/`GUEST_ACTIVITY_PARK_IDS`)
  - the "Benutzer" page stays "Bald verfügbar" for any park not in this set,
  even once it has real guest data.

**Two separate `parks` tables, easy to forget the second one**: the shared
project (`kvpcwlcfgmsmarjtwpsx`) has the park used by the claim pages and
`liftpic_machine_configs`. The **operator** project (`xcrxltiiovpoladpaewd`)
has its own, SEPARATE `parks` table (same `id`, needs `organization_id`,
`name`, `slug`) - without a matching row there, the CRM/Umfrage pages show
"No access to this park" even with a correct password login. Separately,
check `auth.users.raw_app_meta_data->'allowed_park_ids'` on the operator
project for any operator account with a restrictive list (not every account
has one) - add the new park_id there too, or the same error persists even
after the `parks` row exists. User needs to log out/in for a metadata change
to take effect (JWT is cached).

**Photo rotation/aspect ratio**: never assume a new customer's camera
behaves like a park you copied the claim-page template from. Download one
real, recent photo from `photos.storage_path` and look at it directly before
setting `ROTATION_DEGREES`/aspect classes - Tarzans' camera needed 270°
rotation and portrait framing, Imst's and Plose's need 0° and landscape.
Wrong inherited values silently ship otherwise.

**AnyDesk PowerShell**: multi-line input (including here-strings, `@'...'@`)
reliably gets corrupted/reordered over AnyDesk's remote session. Always a
single line, `;`-separated, no backtick line continuations.

**Liftpic Sync resilience** (do this for every new PC, not just when asked):
after the bootstrap installer, also run `scripts/watchdog_einrichten.ps1` as
Administrator. The scheduled task's own "restart on failure" does NOT catch
a clean exit (venv's `python.exe` is a starter stub that exits 0 the instant
it hands off to the real interpreter - Task Scheduler sees that as success,
not failure) - a process that dies mid-session otherwise stays dead until
the next full reboot. This is NOT part of the bootstrap script; it has to be
run separately. Confirmed needed in practice: Plose's agent died exactly
this way mid-session today and sat dead for ~45 minutes before anyone
noticed.
