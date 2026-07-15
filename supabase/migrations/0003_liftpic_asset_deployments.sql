insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'liftpic-assets',
  'liftpic-assets',
  false,
  52428800,
  array['image/png', 'image/jpeg', 'image/bmp', 'image/gif', 'application/octet-stream']
)
on conflict (id) do nothing;

create table if not exists public.liftpic_asset_deployments (
  id uuid primary key default gen_random_uuid(),
  park_id uuid not null references public.parks(id) on delete cascade,
  machine_config_id uuid references public.liftpic_machine_configs(id) on delete cascade,
  machine_id text,
  camera_code text,
  slot text not null,
  label text,
  target_path text not null,
  bucket text not null default 'liftpic-assets',
  storage_path text not null,
  sha256 text,
  content_type text,
  file_size bigint,
  restart_hint text,
  notes text,
  settings jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists liftpic_asset_deployments_active_slot_idx
  on public.liftpic_asset_deployments (
    park_id,
    coalesce(machine_id, ''),
    coalesce(camera_code, ''),
    slot
  )
  where is_active;

create index if not exists liftpic_asset_deployments_park_idx
  on public.liftpic_asset_deployments(park_id, is_active);

alter table public.liftpic_asset_deployments enable row level security;

drop trigger if exists trg_liftpic_asset_deployments_updated_at on public.liftpic_asset_deployments;
create trigger trg_liftpic_asset_deployments_updated_at
before update on public.liftpic_asset_deployments
for each row execute function public.touch_updated_at();

comment on table public.liftpic_asset_deployments is
  'Dashboard-managed files that Liftpic Sync downloads to local Verkaufsautomat/print/logo paths.';

comment on column public.liftpic_asset_deployments.slot is
  'Readable asset slot, for example viewer_main_logo, viewer_default_photo, viewer_print_overlay, print_logo_legacy, jpeg4web_logo.';

comment on column public.liftpic_asset_deployments.target_path is
  'Absolute Windows path on the attraction PC. The local agent also enforces ASSET_SYNC_ALLOWED_ROOTS before writing.';
