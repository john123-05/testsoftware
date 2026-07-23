-- Allow dashboards to read machine_status (health telemetry only: paper, ride
-- counts, device status, log excerpts - no device tokens or secrets). The
-- operator dashboard's park-dashboard-data function reads it via the shared
-- anon key and filters by park_id. Reversible: drop the policy to lock it back.
drop policy if exists "machine_status read for dashboards" on public.machine_status;
create policy "machine_status read for dashboards"
  on public.machine_status
  for select
  to anon, authenticated
  using (true);
