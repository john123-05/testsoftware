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
- If GitHub push fails because Git/auth is missing, finish the local repo and
  report the exact next command once credentials are available.
