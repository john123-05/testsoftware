# Local Asset Sync

Liftpic Sync can also pull dashboard-managed local files onto an attraction PC.
This is meant for Verkaufsautomat logos, preview images, print overlays and old
jpeg4web logos.

Asset sync is a downsync:

```text
Dashboard/Supabase Storage
  -> liftpic-assets Edge Function returns a signed manifest
  -> Liftpic Sync downloads each file
  -> SHA256 is checked when provided
  -> current local file is backed up
  -> target file is replaced atomically
```

## Safety rules

Asset sync is disabled by default:

```text
ASSET_SYNC_ENABLED=false
```

When enabled, the PC may only write inside:

```text
C:\liftpic\samuel_neu
C:\liftpic\imageloader
C:\liftpic\jpeg4web
```

These roots are controlled by:

```text
ASSET_SYNC_ALLOWED_ROOTS=C:\liftpic\samuel_neu;C:\liftpic\imageloader;C:\liftpic\jpeg4web
```

Backups are stored under:

```text
C:\liftpic\liftpic-sync\backups\assets
```

The sync never deletes unknown local files. It only replaces target paths that
come from `liftpic_asset_deployments`.

## Manual test

Run one asset sync without waiting for the service loop:

```powershell
python -m liftpic_sync.cli --env .env assets
```

Expected output:

```json
{
  "applied": 1,
  "failed": 0,
  "fetched": 1,
  "skipped": 0
}
```

## Database table

Migration `0003_liftpic_asset_deployments.sql` creates:

```text
storage bucket: liftpic-assets
liftpic_asset_deployments
```

Important fields:

- `park_id`: which park/customer owns this asset
- `machine_id`: optional, restrict to one PC
- `camera_code`: optional, restrict to one camera/track
- `slot`: readable purpose, for example `viewer_print_overlay`
- `target_path`: exact Windows file path on the PC
- `bucket` and `storage_path`: Supabase Storage source
- `sha256`: optional hash for download validation

## Suggested slots for the inspected PC

- `viewer_main_logo` -> `C:\liftpic\samuel_neu\diabolos.png`
- `viewer_default_photo` -> `C:\liftpic\samuel_neu\preview_logo3.png`
- `viewer_preview_logo` -> `C:\liftpic\samuel_neu\diabolos.png`
- `viewer_single_photo_logo` -> `C:\liftpic\samuel_neu\image1.png`
- `viewer_print_overlay` -> `C:\liftpic\samuel_neu\image1.png`
- `viewer_background` -> `C:\liftpic\samuel_neu\hintergrund.png`
- `viewer_overlay_png` -> `C:\liftpic\samuel_neu\overlay.png`
- `print_logo_legacy` -> `C:\liftpic\imageloader\Vorlage5.bmp`
- `print_border_legacy` -> `C:\liftpic\imageloader\vorlage4.bmp`
- `jpeg4web_logo` -> `C:\liftpic\jpeg4web\fiebich.png`

Start with one harmless logo/preview target on a test PC before replacing print
overlays in production.
