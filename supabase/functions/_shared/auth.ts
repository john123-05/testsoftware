import { serviceClient } from "./supabase.ts";

export type MachineAuth = {
  machineId: string;
  parkId: string;
  cameraCode?: string;
};

function authError(message: string, status = 401): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export async function requireMachineAuth(req: Request): Promise<MachineAuth> {
  const auth = req.headers.get("authorization") ?? "";
  const token = auth.replace(/^Bearer\s+/i, "").trim();
  const expected = Deno.env.get("LIFTPIC_DEVICE_TOKEN") ?? "";
  const machineId = req.headers.get("x-machine-id") ?? "";
  const parkId = req.headers.get("x-park-id") ?? "";

  if (expected && token === expected) {
    if (!machineId || !parkId) {
      throw authError("missing machine or park header", 400);
    }
    return { machineId, parkId };
  }

  const supabase = serviceClient();

  if (token) {
    let query = supabase
      .from("liftpic_machine_configs")
      .select("machine_id, park_id, camera_code")
      .eq("device_token", token)
      .eq("is_active", true)
      .limit(1);
    if (machineId) {
      query = query.eq("machine_id", machineId);
    }
    const { data, error } = await query.maybeSingle();
    if (!error && data) {
      return {
        machineId: data.machine_id,
        parkId: data.park_id,
        cameraCode: data.camera_code ?? undefined,
      };
    }
  }

  // TEMPORARY device-identity fallback (remove after the PC is cleaned up):
  // authenticate by X-Machine-ID + X-Park-ID (a UUID) against an active config.
  if (machineId && parkId) {
    const { data, error } = await supabase
      .from("liftpic_machine_configs")
      .select("machine_id, park_id, camera_code")
      .eq("machine_id", machineId)
      .eq("park_id", parkId)
      .eq("is_active", true)
      .limit(1)
      .maybeSingle();
    if (!error && data) {
      return {
        machineId: data.machine_id,
        parkId: data.park_id,
        cameraCode: data.camera_code ?? undefined,
      };
    }
  }

  throw authError("unauthorized");
}

export function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}
