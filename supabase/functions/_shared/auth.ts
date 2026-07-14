export type MachineAuth = {
  machineId: string;
  parkId: string;
};

export function requireMachineAuth(req: Request): MachineAuth {
  const auth = req.headers.get("authorization") ?? "";
  const token = auth.replace(/^Bearer\s+/i, "").trim();
  const expected = Deno.env.get("LIFTPIC_DEVICE_TOKEN") ?? "";
  if (!expected || token !== expected) {
    throw new Response(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      headers: { "content-type": "application/json" },
    });
  }

  const machineId = req.headers.get("x-machine-id") ?? "";
  const parkId = req.headers.get("x-park-id") ?? "";
  if (!machineId || !parkId) {
    throw new Response(JSON.stringify({ error: "missing machine or park header" }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
  }

  return { machineId, parkId };
}

export function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}
