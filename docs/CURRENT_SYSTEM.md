# Current Liftpic System Observed On This PC

Date inspected: 2026-07-14

## Observed folder flow

Current capture flow on this PC appears to be:

```text
TIScapture / trigger_sender
  -> C:\liftpic\fotos\00046.jpg

AidaTest / Speedshot
  -> reads C:\liftpic\fotos\
  -> writes C:\liftpic\fotos\out\00046_202607141349431395.jpg

PhotoViewerFacebook / sales
  -> displays and sells photos
  -> copies sold photos to C:\liftpic\fotos\qrcode

Liftpic Sync target flow
  -> watches C:\liftpic\fotos\qrcode
  -> renames sold photos with the legacy customer/time/file interleaving formula
  -> copies renamed files to C:\liftpic\fotos\webout
  -> uploads the webout file and metadata

Old jpeg4web config, now reference only
  -> source_folder=c:\Liftpic\fotos\qrcode\
  -> target_folder=c:\Liftpic\fotos\webout\
  -> original_folder=c:\liftpic\fotos\out\

Old uploader.py
  -> uploads SOURCE_DIR directly to Supabase Storage
```

During inspection, `qrcode` and `webout` were empty while `out` contained
processed speed images. The written operational note confirms `qrcode` is the
sold-photo output folder, so the new service defaults to `UPLOAD_SOURCE=qrcode`.

## Filename formula

The legacy online filename is built from:

- `N`: 4-digit customer/internal code
- `T`: 8-digit date code, default `DDMMYYYY`
- `Z`: 4-digit picture code, from the 5-digit camera number without the first
  digit, for example `00047 -> 0047`

Formula:

```text
N[0] T[1] Z[2] N[2] T[0] Z[1] T[7] T[3]
N[1] N[3] Z[0] T[5] T[4] T[2] T[6] Z[3]
```

Example:

```text
N=1234, T=19022026, Z=0860 -> 1963186224002020.jpg
```

The current PC's PhotoViewer settings contain `CustomerNumber=2734`.

## Status files

- `C:\liftpic\samuel_neu\Statistic.txt`: sales/print job lines
- `C:\liftpic\samuel_neu\PrintCount.txt`: remaining paper/print counter, value
  observed as `237`

## Important old files

- `C:\liftpic\TIScapture\dist\config.ini`
- `C:\liftpic\kosel\AidaTest.ini`
- `C:\liftpic\jpeg4web\jpeg4web.ini`
- `C:\liftpic\uploader\uploader.py`
- `C:\liftpic\uploader\uploader_combined.py`
- `C:\liftpic\uploader\speed_bridge.py`

## Known risk

`C:\liftpic\del_pic.bat` deletes:

```text
c:\Liftpic\fotos\*.jpg
c:\Liftpic\fotos\webout\*.jpg
c:\Liftpic\fotos\out\*.jpg
c:\Liftpic\fotos\qrcode\*.jpg
```

This is risky if files are deleted before upload confirmation. The new system
therefore keeps upload state in SQLite and should not rely on local files being
available forever.
