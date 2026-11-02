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

/**
 * Assets for one machine, plus any pending viewer restart order.
 *
 * Some assets only take effect after the kiosk viewer restarts, and
 * hintergrund.png is even held open by it - the agent cannot replace that file
 * at all while the viewer runs. The dashboard therefore parks an order in
 * liftpic_machine_configs.settings.pending_restart. It is handed over here (the
 * machine already polls this endpoint) and cleared once the machine reports
 * back with `restart_ack`.
 *
 * Deliberately stored in the existing jsonb `settings` column: no schema change,
 * nothing to migrate on the production project.
 *
 * The restart part is strictly additive - a machine running an older agent build
 * simply ignores the extra field and behaves exactly as before.
 */
Deno.serve(async (req) => {
  try {
    if (req.method !== "POST") {
      return json({ error: "method not allowed" }, 405);
    }

    const auth = await requireMachineAuth(req);
    const body = await req.json().catch(() => ({}));
    const cameraCode = String(body.camera_code ?? auth.cameraCode ?? "default");
    const restartAck = typeof body.restart_ack === "string" ? body.restart_ack.trim() : "";
    const supabase = serviceClient();

    // Restart order handling is wrapped so a hiccup here can never break the
    // asset delivery the machines rely on.
    let pendingRestart: Record<string, unknown> | null = null;
    try {
      const { data: config } = await supabase
        .from("liftpic_machine_configs")
        .select("id, settings")
        .eq("machine_id", auth.machineId)
        .eq("camera_code", cameraCode)
        .maybeSingle();

      const settings = (config?.settings ?? {}) as Record<string, unknown>;
      pendingRestart = (settings.pending_restart ?? null) as Record<string, unknown> | null;

      if (restartAck && config?.id && pendingRestart) {
        const pendingId = String(pendingRestart.id ?? pendingRestart.requested_at ?? "");
        if (!pendingId || pendingId === restartAck || restartAck === "done") {
          const history = Array.isArray(settings.restart_history) ? settings.restart_history : [];
          await supabase
            .from("liftpic_machine_configs")
            .update({
              settings: {
                ...settings,
                pending_restart: null,
                last_restart_at: new Date().toISOString(),
                restart_history: [
                  { ...pendingRestart, done_at: new Date().toISOString() },
                  ...history,
                ].slice(0, 10),
              },
            })
            .eq("id", config.id);
          pendingRestart = null;
        }
      }
    } catch (_restartErr) {
      pendingRestart = null;
    }

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

    return json({ ok: true, assets, restart_request: pendingRestart });
  } catch (err) {
    if (err instanceof Response) return err;
    return json({ error: String(err) }, 500);
  }
});
