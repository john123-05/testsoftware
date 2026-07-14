import { json, requireMachineAuth } from "../_shared/auth.ts";
import { serviceClient } from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  try {
    const auth = requireMachineAuth(req);
    const body = await req.json();
    const supabase = serviceClient();
    const { error } = await supabase.from("machine_status").upsert({
      machine_id: auth.machineId,
      park_id: auth.parkId,
      park_slug: body.park_slug ?? "unknown-park",
      app_version: body.app_version ?? null,
      last_seen_at: new Date().toISOString(),
      queue_count: body.queue_count ?? 0,
      disk_free_mb: body.disk_free_mb ?? null,
      camera_status: body.camera_status ?? null,
      paper_status: body.paper_status ?? null,
      paper_remaining: body.paper_remaining ?? null,
      last_error: body.last_error ?? null,
      payload: body,
    }, { onConflict: "machine_id" });
    if (error) throw error;
    return json({ ok: true });
  } catch (err) {
    if (err instanceof Response) return err;
    return json({ error: String(err) }, 500);
  }
});
