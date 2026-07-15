# Current Liftpic System Observed On This PC

Date inspected: 2026-07-14

Overlay/asset inspection updated: 2026-07-15

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

## Local viewer, overlay and print assets

The active Verkaufsautomat/PhotoViewer config is:

```text
C:\liftpic\samuel_neu\Settings.xml
```

Relevant fields observed in that file:

- `LogoFilename`: `c:\liftpic\samuel_neu\diabolos.png`
- `DefaultPhoto`: `C:\liftpic\samuel_neu\preview_logo3.png`
- `PreviewLogo`: `c:\liftpic\samuel_neu\diabolos.png`
- `Split3LogoFilename`: `c:\liftpic\samuel_neu\logo_saalfelden.png`
- `SinglePhotoLogoFilename`: `C:\liftpic\samuel_neu\image1.png`
- `OverlayImageFilename`: `C:\liftpic\samuel_neu\image1.png`
- `ShowOverlayOnPrint`: `true`
- `ShowOverlayOnUpload`: `0`
- `QrCodePrintedCopyFolder`: `c:\liftpic\fotos\qrcode`

Files/folders found around the viewer:

- `C:\liftpic\samuel_neu\overlay.png`
- `C:\liftpic\samuel_neu\image1.png`
- `C:\liftpic\samuel_neu\hintergrund.png`
- `C:\liftpic\samuel_neu\Bilderrahmen5.png`
- `C:\liftpic\samuel_neu\logo.png`, `logo2.png`, `logo4.PNG`
- `C:\liftpic\samuel_neu\preview_logo.PNG`, `preview_logo22.PNG`
- `C:\liftpic\samuel_neu\styles\*.png`
- `C:\liftpic\samuel_neu\styles_4k\*.png`

Legacy print/image loader files:

- `C:\liftpic\imageloader\PrintSettings.ini`
- `C:\liftpic\imageloader\PrintSettings1.ini`
- `C:\liftpic\imageloader\PrintSettings2.ini`
- `C:\liftpic\imageloader\Vorlage*.bmp`
- `C:\liftpic\imageloader\vorlage4.bmp`
- `C:\liftpic\imageloader\Vorlage5.bmp`
- `C:\liftpic\imageloader\overlay_berer.JPG`
- `C:\liftpic\imageloader\mask.bmp`

Legacy jpeg4web logo config:

- `C:\liftpic\jpeg4web\jpeg4web.ini`
- `logo_file=c:\Liftpic\jpeg4web\fiebich.png`

The new Liftpic Sync asset downsync does not edit `Settings.xml` yet. It only
replaces dashboard-approved asset files at explicit target paths, with a local
backup before overwrite.

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
