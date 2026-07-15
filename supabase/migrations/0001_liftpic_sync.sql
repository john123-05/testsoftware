create table if not exists public.parks (
  id uuid primary key,
  slug text not null unique,
  name text,
  created_at timestamptz not null default now()
);

create table if not exists public.machine_status (
  machine_id text primary key,
  park_id uuid references public.parks(id),
  park_slug text not null,
  app_version text,
  last_seen_at timestamptz not null default now(),
  queue_count integer not null default 0,
  disk_free_mb integer,
  camera_status text,
  paper_status text,
  paper_remaining integer,
  last_error text,
  payload jsonb not null default '{}'::jsonb
);

alter table public.machine_status add column if not exists camera_code text;
alter table public.machine_status add column if not exists photos_taken_today integer not null default 0;
alter table public.machine_status add column if not exists photos_sold_today integer not null default 0;
alter table public.machine_status add column if not exists photo_conversion_today numeric;

create table if not exists public.photo_events (
  id uuid primary key default gen_random_uuid(),
  park_id uuid references public.parks(id),
  park_slug text not null,
  machine_id text not null,
  event_key text not null,
  camera_code text,
  capture_id text not null,
  legacy_filename text not null,
  legacy_code text,
  time_code text,
  file_code text,
  raw_local_name text,
  processed_storage_path text,
  raw_storage_path text,
  captured_at timestamptz,
  speed_kmh numeric,
  speed_status text not null default 'missing',
  upload_status text not null default 'pending',
  checksum_sha256 text,
  error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(machine_id, event_key)
);

alter table public.photo_events add column if not exists event_key text;
alter table public.photo_events add column if not exists camera_code text;

create unique index if not exists photo_events_machine_event_key_idx
  on public.photo_events(machine_id, event_key)
  where event_key is not null;

create table if not exists public.park_photo_ride_daily (
  id uuid primary key default gen_random_uuid(),
  park_id uuid references public.parks(id),
  park_slug text not null,
  machine_id text not null,
  camera_code text not null default 'default',
  business_date date not null,
  photos_taken_count integer not null default 0,
  photos_sold_count integer not null default 0,
  conversion_rate numeric,
  first_capture_at timestamptz,
  last_capture_at timestamptz,
  last_sale_at timestamptz,
  speed_ok_count integer not null default 0,
  last_seen_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(machine_id, camera_code, business_date)
);

alter table public.parks enable row level security;
alter table public.machine_status enable row level security;
alter table public.photo_events enable row level security;
alter table public.park_photo_ride_daily enable row level security;

create index if not exists photo_events_park_created_idx
  on public.photo_events(park_id, created_at desc);

create index if not exists photo_events_legacy_filename_idx
  on public.photo_events(legacy_filename);

create index if not exists park_photo_ride_daily_park_date_idx
  on public.park_photo_ride_daily(park_id, business_date desc);

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_photo_events_updated_at on public.photo_events;
create trigger trg_photo_events_updated_at
before update on public.photo_events
for each row execute function public.touch_updated_at();

drop trigger if exists trg_park_photo_ride_daily_updated_at on public.park_photo_ride_daily;
create trigger trg_park_photo_ride_daily_updated_at
before update on public.park_photo_ride_daily
for each row execute function public.touch_updated_at();
