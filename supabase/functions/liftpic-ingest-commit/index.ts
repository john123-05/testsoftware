import { json, requireMachineAuth } from "../_shared/auth.ts";
import { serviceClient } from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  try {
    const auth = requireMachineAuth(req);
    const body = await req.json();
    const captureId = body.capture_id;
    const storagePath = body.storage_path;
    if (!captureId || !storagePath) {
      return json({ error: "capture_id and storage_path are required" }, 400);
    }

    const supabase = serviceClient();
    const { error } = await supabase
      .from("photo_events")
      .update({
        upload_status: "uploaded",
        processed_storage_path: storagePath,
        raw_storage_path: body.raw_storage_path ?? null,
        error: null,
      })
      .eq("machine_id", auth.machineId)
      .eq("capture_id", captureId);
    if (error) throw error;

    return json({ ok: true });
  } catch (err) {
    if (err instanceof Response) return err;
    return json({ error: String(err) }, 500);
  }
});
