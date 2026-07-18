# Liftpictures Ecosystem Map

Read this first if you are an LLM or new maintainer opening this repo
cold. It explains the whole company system landscape, which repo does
what, where the databases live, and the known history you would
otherwise painfully rediscover. Last updated 2026-07-18.

## What the company does

Liftpictures builds automated photo systems for ride attractions
(alpine coasters, summer toboggans, adventure parks): a light barrier
triggers a camera, the photo is processed (speed overlay, date), shown
on a Verkaufsautomat (vending kiosk), sold as print with a QR code,
and/or offered online where guests claim their photo via that QR code.

People:

- **John** - builds all the new software (dashboards, claim pages, this
  repo), works with LLM agents (Claude, Codex).
- **Tom ("Papa")** - built the legacy on-PC programs over many years,
  does all physical installs and field support. His knowledge is
  captured in `docs/PC_SETUP_CHECKLIST.md`.

Customers (as of July 2026):

- **Imster Bergbahnen (Imst, Austria)** - Alpine Coaster. Live, busiest
  customer. Kiosk sales (`parks.price_per_photo_cents` set), photos
  claimable at `liftpictures-fotos.de`.
- **SIA "CSS-ALPINE" / Tarzans Sigulda (Latvia)** - adventure park, new
  customer. Claim page at `liftpictures-fotos-tarzans.de`. Park password
  reference: stored in staff dashboard Passwoerter page.
- **Plose (South Tyrol)** - webshop/claim funnel with its own repo and
  ranking page. NOTE: a similarly named test park "Plose Plosebob" plus
  "Adventure Land" and "TestPark" were deleted from the DB on 2026-07-17
  (full local backup taken first). Only the real "Plose" park remains.
- Traveling **Schausteller** customers with mobile automats (coin +
  credit card terminal, no online part).

## Repos

| Repo | Purpose | Deploy |
| --- | --- | --- |
| `john123-05/testsoftware` (THIS repo) | Liftpic Sync: the on-PC agent that renames sold photos to the legacy code format, uploads them, counts rides, syncs dashboard-managed assets down, reports health | Installed on attraction PCs via bootstrap PowerShell + pairing code from the dashboard |
| `tomnotes2/testsoftware` | STALE initial copy of this repo (single commit from the first Codex session). Do not use; kept only because it is linked from an old chat | - |
| `john123-05/dashboard2` | Two apps in one: customer-facing Operator Dashboard (per-park login) AND internal Staff Dashboard under `/staff/*` (admin login). The Staff Dashboard's "Kunden Management -> Liftpic" tab is the control panel for THIS repo's agents | `dashboard-liftpictures.com`, Netlify auto-deploys from `main` |
| `john123-05/imst` | Photo claim page for Imst (`liftpictures-fotos.de`) plus `tarzans/` subfolder for the Tarzans claim page (`liftpictures-fotos-tarzans.de`). Multi-language (en fallback), QR `?code=` claim flow | CAUTION: has a bolt.new publish gate - `git push` alone does NOT deploy; someone must press Publish in bolt.new |
| Plose repo (local `plose-v2-2`) | Plose claim funnel, ranking, webshop | own pipeline |

## Supabase projects (two, do not confuse)

**`kvpcwlcfgmsmarjtwpsx` - shared content/production project.**
Owns everything photo/park related and staff auth:
`parks`, `photos`, `photo_claims`, `attractions`, `park_cameras`,
`park_path_prefixes`, `admin_users` (staff logins), `support_tickets`,
`park_photo_sales_daily` (permanent revenue rollup - raw `photos` rows
are hard-deleted after ~30 days, this table is the durable record),
`park_photo_ride_daily`, and this repo's tables:
`liftpic_machine_configs`, `liftpic_asset_deployments`,
`machine_status`, `photo_events`, plus the private `liftpic-assets`
storage bucket. Edge functions: `liftpic-config`, `liftpic-assets`,
`liftpic-ingest-begin/commit`, `liftpic-status`, and the dashboard's
`admin-*` functions.

**`xcrxltiiovpoladpaewd` - operator dashboard project.**
Owns operator-side auth and webshop config: `park_access`
(+ `verify_park_access` RPC - the REAL park password auth),
`media_assets`, `stripe_product_selections`, `park-dashboard-data`
edge function (parses kiosk log files for revenue), `stripe-revenue`.
Stripe here has been test-mode only so far.

Working conventions (established, do not break):

- Schema/data changes are NEVER executed directly by agents; SQL is
  handed to John to run in the Supabase SQL editor.
- Never commit secrets, service-role keys, device tokens, or plaintext
  passwords into any repo.
- The PC agent never holds a service-role key; it authenticates with its
  per-machine `device_token` obtained via pairing.

## The photo pipeline, end to end

```text
Light barrier -> camera26.exe/TIScapture   writes C:\liftpic\fotos\00047.jpg
AidaTest (speed via COM port)              writes fotos\out\00047_<date><time><speed>.jpg
PhotoViewerFacebook "Samuel" (sales UI)    copies sold photos to fotos\qrcode,
                                           prints with QR code
Liftpic Sync (THIS repo)                   renames qrcode files to the legacy
                                           16-digit code, stages to fotos\webout,
                                           uploads via edge functions, heartbeats
Claim pages (imst repo etc.)               guest scans QR -> /claim?code=<16 digits>
                                           -> find_claim_photo RPC -> unlock/purchase
Nightly del_pic.bat                        wipes all local photo folders; camera
                                           restarts at 00000.jpg (Nikon does NOT reset!)
```

The 16-digit filename format and interleaving formula are documented in
`docs/CURRENT_SYSTEM.md`. Key facts: 4 digits camera/customer code (N),
8 digits date (T), 4 digits picture number (Z, first digit of the
5-digit camera counter dropped). The last 4 digits AidaTest appends to
the intermediate filename are SPEED, not part of the online code.

## Known incident: "Foto nicht gefunden" (Imst, July 2026)

Root cause is architectural: the QR-code PRINT step (inside Samuel,
closed source, no repo access) and the upload step each compute the
16-digit code independently. When they disagree (observed: one drifting
digit in the picture-number slots), the printed QR matches no uploaded
photo. Mitigations shipped in the claim pages / shared DB:

- client-side retry (`resolveClaimPhotoWithRetry`, ~14s) for genuine
  timing races;
- `find_claim_photo` RPC fallback path 4: match on the camera+date
  fingerprint (all positions except the 4 picture-number slots) ONLY
  when exactly one candidate exists - deliberately never guesses among
  multiple candidates (explicit product decision: never risk showing a
  stranger's photo).

The real fix - and a long-term goal of this repo - is a single source
of truth: code generation must happen in ONE program. That requires
Samuel to consume codes from Liftpic Sync instead of computing its own,
i.e. Tom's involvement.

## What the dashboard controls on each PC (already live)

Staff Dashboard -> Kunden Management -> Liftpic:

- create a machine, get a pairing code; one-command install on the PC
  (`install_liftpic_sync_bootstrap.ps1 -PairingCode XXXX`) pulls the
  entire config (park, camera code, legacy customer code, folder paths,
  device token) from `liftpic_machine_configs`;
- per-machine switches: mode (`sold_only` / `all_photos` /
  `count_only`), QR, speed, ride counting, shadow mode;
- asset slots (Verkaufsautomat logo, print overlay, ...): upload a file
  in the dashboard, the PC's `AssetSyncWorker` polls, downloads,
  verifies SHA256, backs up the old file, atomically replaces the
  target (e.g. `C:\liftpic\samuel_neu\overlay.png`). It never edits
  `Settings.xml`;
- heartbeat monitoring: queue depth, paper counter (from
  `PrintCount.txt`), coin/terminal/printer/camera health parsed
  read-only from legacy logs, `last_seen_at`.

## Rollout status (2026-07-18)

- Test PC (John's Windows machine): full chain built and tested; CSS-
  ALPINE/Tarzans used as the trial integration.
- Imst and Schausteller customers: still on the pure legacy chain.
- Next steps: shadow-mode run on a real customer PC comparing against
  the old uploader, then cut over; only after that consider moving code
  generation out of Samuel.

## Reading order for new agents

1. This file.
2. `README.md` - what Liftpic Sync is and safe-rollout rules.
3. `docs/CURRENT_SYSTEM.md` - observed legacy PC state + filename formula.
4. `docs/PC_SETUP_CHECKLIST.md` - Tom's field wisdom (hardware/Windows).
5. `AGENTS.md` - working rules and implementation notes.
6. `docs/PARK_CONFIG.md`, `docs/INSTALL_WINDOWS.md`, `docs/ASSET_SYNC.md`,
   `docs/SUPABASE_SETUP.md` - operational details.
