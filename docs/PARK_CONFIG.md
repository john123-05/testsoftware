# Park Configuration

Each attraction/client PC should use the same code and a different `.env`.
For new installs, prefer pairing from the Staff Dashboard instead of typing all
values by hand:

Start from:

```powershell
copy config\park.example.env .env
python -m liftpic_sync.cli --env .env pair --code YOURCODE
```

## Required values

- `PARK_SLUG`: short readable code, for example `plose-plosebob`
- `PARK_ID`: Supabase UUID for the park/attraction
- `CUSTOMER_CODE`: four-digit customer code used in legacy filenames
- `MACHINE_ID`: stable PC/camera identifier, for example `plose-pc1`
- `CAMERA_CODE`: stable camera/track code under the machine, for example
  `cam1` or `plosebob-main`
- `DEVICE_TOKEN`: secret token issued for this machine
- `SUPABASE_FUNCTIONS_URL`: project functions URL

When pairing succeeds, `PARK_SLUG`, `PARK_ID`, `CUSTOMER_CODE`, `MACHINE_ID`,
`CAMERA_CODE`, `DEVICE_TOKEN`, folder paths and mode flags are written into
`.env` automatically. Manual editing should normally be limited to Supabase
project URLs or special local folder paths.

## Folder values

Default for the current inspected PC:

```text
RAW_DIR=C:\liftpic\fotos
PROCESSED_DIR=C:\liftpic\fotos\out
WEBOUT_DIR=C:\liftpic\fotos\webout
QRCODE_DIR=C:\liftpic\fotos\qrcode
UPLOAD_SOURCE=qrcode
STAGE_IN_SHADOW=false
STATISTIC_FILE=C:\liftpic\samuel_neu\Statistic.txt
PRINT_COUNT_FILE=C:\liftpic\samuel_neu\PrintCount.txt
CAMERA_CODE=cam1
RIDE_COUNT_ENABLED=true
RIDE_COUNT_SOURCE=processed,raw
```

Use `UPLOAD_SOURCE=qrcode` for the current sold-photo flow. Use
`UPLOAD_SOURCE=webout` only if another attraction already stages renamed files
there. Use `UPLOAD_SOURCE=all` only for diagnostics because it may queue unsold
raw/processed photos.

## Ride counts without uploading every photo

`RIDE_COUNT_ENABLED=true` makes the service count every camera event locally.
The default `RIDE_COUNT_SOURCE=processed,raw` reads `fotos\out` first because
AidaTest filenames contain timestamp and speed, then uses raw `fotos` as a
fallback. Raw and processed files for the same ride are de-duplicated by:

```text
MACHINE_ID + CAMERA_CODE + business date + five-digit capture number
```

The heartbeat sends small daily counters such as `photos_taken_today`,
`photos_sold_today`, and `ride_rollups`. It does not upload unbought JPEGs.

## Local logo and overlay asset sync

For dashboard-managed local files, enable:

```text
ASSET_SYNC_ENABLED=true
ASSET_SYNC_SECONDS=300
ASSET_BACKUP_DIR=C:\liftpic\liftpic-sync\backups\assets
ASSET_SYNC_ALLOWED_ROOTS=C:\liftpic\samuel_neu;C:\liftpic\imageloader;C:\liftpic\jpeg4web
```

This lets the PC download assigned files from Supabase and replace only allowed
local target paths such as viewer logos, `image1.png` print overlays, old
`imageloader` templates or the old `jpeg4web` logo. Test manually with:

```powershell
python -m liftpic_sync.cli --env .env assets
```

More detail is in `docs/ASSET_SYNC.md`.

## Legacy filename behavior

The system keeps legacy-compatible names online but stores clean metadata too.

Example:

```text
1963186224002020.jpg
```

Parsed as:

- legacy code: `1963`
- time code: `18622400`
- file code: `2020`

For newly staged sold photos, the service uses the old interleaving formula:

```text
N[0]+T[1]+Z[2]+N[2]+T[0]+Z[1]+T[7]+T[3]+
N[1]+N[3]+Z[0]+T[5]+T[4]+T[2]+T[6]+Z[3]+".jpg"
```

Where `N` is the customer/internal code, `T` defaults to `DDMMYYYY`, and `Z` is
the 5-digit camera photo number without its first digit.

The exact code policy is centralized in `src/liftpic_sync/filename_codec.py` so
it can be tested and changed once instead of scattered across scripts.
