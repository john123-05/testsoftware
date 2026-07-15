# Supabase Setup

Liftpic Sync uses Supabase Edge Functions as the trusted boundary. The PC sends
a machine token to the function. The function uses the service role key inside
Supabase only, creates or updates metadata rows, and returns a signed Storage
upload target.

## Required Supabase pieces

- Storage bucket, for example `test` or `liftpic-photos`
- SQL migration from `supabase/migrations/0001_liftpic_sync.sql`
- Edge Functions:
  - `liftpic-ingest-begin`
  - `liftpic-ingest-commit`
  - `liftpic-status`

`liftpic-status` stores both machine health and daily ride rollups in
`park_photo_ride_daily`. These rollups are small JSON/SQL counters
(`photos_taken_count`, `photos_sold_count`, conversion, last capture time).
They are separate from Storage uploads, so unbought JPEGs do not need to be
sent to Supabase.

## Function secrets

Configure these in Supabase, not in Git:

```text
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
LIFTPIC_BUCKET=test
LIFTPIC_DEVICE_TOKEN=...
```

`LIFTPIC_DEVICE_TOKEN` is the shared machine token for the first version. Later
it can be replaced with per-machine tokens stored in a table.

## PC `.env`

The attraction PC needs:

```text
SUPABASE_FUNCTIONS_URL=https://YOUR_PROJECT.supabase.co/functions/v1
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=...
DEVICE_TOKEN=...
```

The anon key is public-ish and is used only for the official signed-upload
client path. The service role key must never be present on an attraction PC.

## Deploy commands

When Supabase CLI is installed:

```powershell
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
supabase functions deploy liftpic-ingest-begin
supabase functions deploy liftpic-ingest-commit
supabase functions deploy liftpic-status
```

References:

- https://supabase.com/docs/guides/functions
- https://supabase.com/docs/reference/python/storage-from-uploadtosignedurl
