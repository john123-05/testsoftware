import { json, requireMachineAuth } from "../_shared/auth.ts";
import { serviceClient } from "../_shared/supabase.ts";

type ConfigRow = {
  id: string;
  park_id: string;
  attraction_id: string | null;
  machine_id: string;
  machine_label: string;
  camera_code: string;
  camera_label: string;
  legacy_customer_code: string;
  mode: string;
  qr_enabled: boolean;
  speed_enabled: boolean;
  count_rides_enabled: boolean;
  upload_all_photos: boolean;
  shadow_mode: boolean;
  raw_dir: string;
  processed_dir: string;
  qrcode_dir: string;
  webout_dir: string;
  statistic_file: string;
  print_count_file: string;
  paper_warn_remaining: number;
  paper_capacity: number;
  pairing_status: string;
  device_token: string;
  parks?: { slug?: string; name?: string } | null;
};

function cleanCode(value: unknown): string {
  return typeof value === "string" ? value.trim().toUpperCase() : "";
}

function publicConfig(row: ConfigRow) {
  return {
    id: row.id,
    park_id: row.park_id,
    park_slug: row.parks?.slug ?? "unknown-park",
    attraction_id: row.attraction_id,
    machine_id: row.machine_id,
    machine_label: row.machine_label,
    camera_code: row.camera_code,
    camera_label: row.camera_label,
    legacy_customer_code: row.legacy_customer_code,
    mode: row.mode,
    qr_enabled: row.qr_enabled,
    speed_enabled: row.speed_enabled,
    count_rides_enabled: row.count_rides_enabled,
    upload_all_photos: row.upload_all_photos,
    shadow_mode: row.shadow_mode,
    raw_dir: row.raw_dir,
    processed_dir: row.processed_dir,
    qrcode_dir: row.qrcode_dir,
    webout_dir: row.webout_dir,
    statistic_file: row.statistic_file,
    print_count_file: row.print_count_file,
    paper_warn_remaining: row.paper_warn_remaining,
    paper_capacity: row.paper_capacity,
  };
}

Deno.serve(async (req) => {
  try {
    if (req.method !== "POST") {
      return json({ error: "method not allowed" }, 405);
    }

    const body = await req.json().catch(() => ({}));
    const supabase = serviceClient();
    const pairingCode = cleanCode(body.pairing_code);

    let query = supabase
      .from("liftpic_machine_configs")
      .select("*, parks(slug, name)")
      .eq("is_active", true)
      .limit(1);

    if (pairingCode) {
      query = query.eq("pairing_code", pairingCode).neq("pairing_status", "disabled");
    } else {
      const auth = await requireMachineAuth(req);
      query = query.eq("machine_id", auth.machineId).eq("park_id", auth.parkId);
      if (auth.cameraCode) query = query.eq("camera_code", auth.cameraCode);
    }

    const { data, error } = await query.maybeSingle();
    if (error) throw error;
    if (!data) {
      return json({ error: "pairing code not found" }, 404);
    }

    const row = data as ConfigRow;
    await supabase
      .from("liftpic_machine_configs")
      .update({
        pairing_status: "paired",
        last_seen_at: new Date().toISOString(),
      })
      .eq("id", row.id);

    return json({
      ok: true,
      config: publicConfig(row),
      device_token: row.device_token,
    });
  } catch (err) {
    if (err instanceof Response) return err;
    return json({ error: String(err) }, 500);
  }
});
