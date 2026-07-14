# Park Configuration

Each attraction/client PC should use the same code and a different `.env`.

Start from:

```powershell
copy config\park.example.env .env
```

## Required values

- `PARK_SLUG`: short readable code, for example `plose-plosebob`
- `PARK_ID`: Supabase UUID for the park/attraction
- `CUSTOMER_CODE`: four-digit customer code used in legacy filenames
- `MACHINE_ID`: stable PC/camera identifier, for example `plose-pc1`
- `DEVICE_TOKEN`: secret token issued for this machine
- `SUPABASE_FUNCTIONS_URL`: project functions URL

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
```

Use `UPLOAD_SOURCE=qrcode` for the current sold-photo flow. Use
`UPLOAD_SOURCE=webout` only if another attraction already stages renamed files
there. Use `UPLOAD_SOURCE=all` only for diagnostics because it may queue unsold
raw/processed photos.

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
