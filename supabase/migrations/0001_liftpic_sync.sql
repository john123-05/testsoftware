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

create table if not exists public.photo_events (
  id uuid primary key default gen_random_uuid(),
  park_id uuid references public.parks(id),
  park_slug text not null,
  machine_id text not null,
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
  unique(machine_id, capture_id)
);

alter table public.parks enable row level security;
alter table public.machine_status enable row level security;
alter table public.photo_events enable row level security;

create index if not exists photo_events_park_created_idx
  on public.photo_events(park_id, created_at desc);

create index if not exists photo_events_legacy_filename_idx
  on public.photo_events(legacy_filename);

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
