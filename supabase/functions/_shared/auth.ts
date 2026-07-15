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

  if (!token) {
    throw authError("unauthorized");
  }

  const supabase = serviceClient();
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
  if (error || !data) {
    throw authError("unauthorized");
  }

  return {
    machineId: data.machine_id,
    parkId: data.park_id,
    cameraCode: data.camera_code ?? undefined,
  };
}

export function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}
