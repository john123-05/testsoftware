import { json, requireMachineAuth } from "../_shared/auth.ts";
import { serviceClient } from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  try {
    const auth = await requireMachineAuth(req);
    const body = await req.json();
    const supabase = serviceClient();
    const { error } = await supabase.from("machine_status").upsert({
      machine_id: auth.machineId,
      park_id: auth.parkId,
      park_slug: body.park_slug ?? "unknown-park",
      app_version: body.app_version ?? null,
      camera_code: body.camera_code ?? null,
      last_seen_at: new Date().toISOString(),
      queue_count: body.queue_count ?? 0,
      disk_free_mb: body.disk_free_mb ?? null,
      camera_status: body.camera_status ?? null,
      paper_status: body.paper_status ?? null,
      paper_remaining: body.paper_remaining ?? null,
      photos_taken_today: body.photos_taken_today ?? 0,
      photos_sold_today: body.photos_sold_today ?? 0,
      photo_conversion_today: body.photo_conversion_today ?? null,
      last_error: body.last_error ?? null,
      payload: body,
    }, { onConflict: "machine_id" });
    if (error) throw error;

    await supabase
      .from("liftpic_machine_configs")
      .update({
        last_seen_at: new Date().toISOString(),
        last_status: body,
      })
      .eq("machine_id", auth.machineId)
      .eq("camera_code", body.camera_code ?? auth.cameraCode ?? "default");

    const rideRollups = Array.isArray(body.ride_rollups) ? body.ride_rollups : [];
    if (rideRollups.length > 0) {
      const rows = rideRollups
        .filter((item) => item && item.business_date)
        .map((item) => ({
          park_id: auth.parkId,
          park_slug: item.park_slug ?? body.park_slug ?? "unknown-park",
          machine_id: auth.machineId,
          camera_code: item.camera_code ?? body.camera_code ?? "default",
          business_date: item.business_date,
          photos_taken_count: item.photos_taken_count ?? 0,
          photos_sold_count: item.photos_sold_count ?? 0,
          conversion_rate: item.conversion_rate ?? null,
          first_capture_at: item.first_capture_at ?? null,
          last_capture_at: item.last_capture_at ?? null,
          last_sale_at: item.last_sale_at ?? null,
          speed_ok_count: item.speed_ok_count ?? 0,
          last_seen_at: new Date().toISOString(),
          payload: item,
        }));

      if (rows.length > 0) {
        const { error: rollupError } = await supabase
          .from("park_photo_ride_daily")
          .upsert(rows, { onConflict: "machine_id,camera_code,business_date" });
        if (rollupError) throw rollupError;
      }
    }

    return json({ ok: true });
  } catch (err) {
    if (err instanceof Response) return err;
    return json({ error: String(err) }, 500);
  }
});
