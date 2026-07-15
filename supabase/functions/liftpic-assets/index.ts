import { json, requireMachineAuth } from "../_shared/auth.ts";
import { serviceClient } from "../_shared/supabase.ts";

type AssetRow = {
  id: string;
  park_id: string;
  machine_id: string | null;
  camera_code: string | null;
  slot: string;
  label: string | null;
  target_path: string;
  bucket: string;
  storage_path: string;
  sha256: string | null;
  content_type: string | null;
  file_size: number | null;
  restart_hint: string | null;
  updated_at: string;
};

Deno.serve(async (req) => {
  try {
    if (req.method !== "POST") {
      return json({ error: "method not allowed" }, 405);
    }

    const auth = await requireMachineAuth(req);
    const body = await req.json().catch(() => ({}));
    const cameraCode = String(body.camera_code ?? auth.cameraCode ?? "default");
    const supabase = serviceClient();

    const { data, error } = await supabase
      .from("liftpic_asset_deployments")
      .select("id, park_id, machine_id, camera_code, slot, label, target_path, bucket, storage_path, sha256, content_type, file_size, restart_hint, updated_at")
      .eq("park_id", auth.parkId)
      .eq("is_active", true)
      .order("slot", { ascending: true });
    if (error) throw error;

    const rows = ((data ?? []) as AssetRow[]).filter((row) => {
      const machineMatches = !row.machine_id || row.machine_id === auth.machineId;
      const cameraMatches = !row.camera_code || row.camera_code === cameraCode;
      return machineMatches && cameraMatches;
    });

    const assets = [];
    for (const row of rows) {
      const { data: signed, error: signedError } = await supabase.storage
        .from(row.bucket)
        .createSignedUrl(row.storage_path, 600);
      if (signedError) throw signedError;
      assets.push({
        id: row.id,
        slot: row.slot,
        label: row.label,
        target_path: row.target_path,
        bucket: row.bucket,
        storage_path: row.storage_path,
        signed_url: signed.signedUrl,
        sha256: row.sha256,
        content_type: row.content_type,
        file_size: row.file_size,
        restart_hint: row.restart_hint,
        updated_at: row.updated_at,
      });
    }

    await supabase
      .from("liftpic_machine_configs")
      .update({ last_seen_at: new Date().toISOString() })
      .eq("machine_id", auth.machineId)
      .eq("camera_code", cameraCode);

    return json({ ok: true, assets });
  } catch (err) {
    if (err instanceof Response) return err;
    return json({ error: String(err) }, 500);
  }
});
