import { json, requireMachineAuth } from "../_shared/auth.ts";
import { serviceClient } from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  try {
    const auth = await requireMachineAuth(req);
    const body = await req.json();
    const captureId = body.capture_id;
    const eventKey = body.event_key;
    const storagePath = body.storage_path;
    if (!captureId || !storagePath) {
      return json({ error: "capture_id and storage_path are required" }, 400);
    }

    const supabase = serviceClient();
    let query = supabase
      .from("photo_events")
      .update({
        upload_status: "uploaded",
        processed_storage_path: storagePath,
        raw_storage_path: body.raw_storage_path ?? null,
        error: null,
      })
      .eq("machine_id", auth.machineId);
    query = eventKey ? query.eq("event_key", eventKey) : query.eq("capture_id", captureId);

    const { error } = await query;
    if (error) throw error;

    return json({ ok: true });
  } catch (err) {
    if (err instanceof Response) return err;
    return json({ error: String(err) }, 500);
  }
});
