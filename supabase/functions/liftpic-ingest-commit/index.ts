import { json, requireMachineAuth } from "../_shared/auth.ts";
import { serviceClient } from "../_shared/supabase.ts";

const SENTINEL_PARK_ID = "11111111-1111-1111-1111-111111111111";

// Extract the 16-digit legacy claim code from an uploaded file name/path.
// The uploader names sold photos "<16 digits>.jpg" (the jpeg4web interleaved
// code), so the file stem IS the code the printed QR encodes.
function extractExternalCode(...candidates: Array<string | null | undefined>): string | null {
  for (const candidate of candidates) {
    if (!candidate) continue;
    const base = candidate.split("/").pop() ?? candidate;
    const stem = base.replace(/\.[^.]+$/, "");
    if (/^\d{16}$/.test(stem)) return stem;
    if (/^\d{20}$/.test(stem)) return stem.slice(0, 16);
    const prefixed = stem.match(/^(\d{16})[_-]/);
    if (prefixed) return prefixed[1];
  }
  return null;
}

type PhotoEventRow = {
  park_id: string | null;
  camera_code: string | null;
  legacy_filename: string | null;
  time_code: string | null;
  file_code: string | null;
  captured_at: string | null;
  speed_kmh: number | null;
  processed_storage_path: string | null;
  metadata: Record<string, unknown> | null;
};

// Mirror an uploaded sold photo into the claimable `photos` table so the QR
// claim pages (find_claim_photo fast path) resolve it. Never throws: a photos
// write must not fail the upload commit.
async function writeClaimablePhoto(
  supabase: ReturnType<typeof serviceClient>,
  ev: PhotoEventRow,
  bucket: string,
  storagePath: string,
): Promise<{ claimable: boolean; external_code: string | null; reason?: string }> {
  const parkId = ev.park_id;
  if (!parkId || parkId === SENTINEL_PARK_ID) {
    return { claimable: false, external_code: null, reason: "no park_id on photo_event" };
  }

  // Only actually-sold (QR-sourced) photos become claimable. The scanner sets
  // sold_source_path only for photos taken from the qrcode folder. This keeps
  // one claimable photos row == one sold photo (so the park_photo_sales_daily
  // rollup trigger is not inflated by all_photos-mode uploads).
  const soldSourcePath = ev.metadata?.sold_source_path;
  if (typeof soldSourcePath !== "string" || !soldSourcePath) {
    return { claimable: false, external_code: null, reason: "not a sold (qrcode) photo" };
  }

  const externalCode = extractExternalCode(ev.legacy_filename, storagePath, ev.processed_storage_path);
  if (!externalCode) {
    return { claimable: false, external_code: null, reason: "no 16-digit code in filename" };
  }

  const customerCode =
    (typeof ev.metadata?.customer_code === "string" ? (ev.metadata.customer_code as string) : null) ??
    ev.camera_code ??
    null;

  const { data: park } = await supabase
    .from("parks")
    .select("price_per_photo_cents")
    .eq("id", parkId)
    .maybeSingle();
  const priceCents = Number.isFinite(Number(park?.price_per_photo_cents))
    ? Number(park?.price_per_photo_cents)
    : 300;

  const row = {
    park_id: parkId,
    storage_bucket: bucket,
    storage_path: storagePath,
    external_code: externalCode,
    // Existing rows (and find_claim_photo's own fallback) store the legacy
    // customer code in camera_code so the attraction-assignment trigger keys
    // off it. Keep that convention.
    camera_code: customerCode,
    source_customer_code: customerCode,
    source_time_code: ev.time_code,
    source_file_code: ev.file_code,
    source_speed_kmh: ev.speed_kmh,
    speed_kmh: ev.speed_kmh,
    captured_at: ev.captured_at ?? new Date().toISOString(),
    is_paid: false,
    price_cents: priceCents,
    currency: "eur",
  };

  const { error } = await supabase
    .from("photos")
    .upsert(row, { onConflict: "park_id,storage_bucket,storage_path", ignoreDuplicates: false });

  if (error) {
    // A different photo may already own this external_code (unique). Treat as
    // already-claimable and never fail the commit over a photos write.
    return { claimable: true, external_code: externalCode, reason: `photos upsert: ${error.message}` };
  }
  return { claimable: true, external_code: externalCode };
}

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

    const bucket = Deno.env.get("LIFTPIC_BUCKET") ?? "test";
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

    const { data: events, error } = await query.select(
      "park_id, camera_code, legacy_filename, time_code, file_code, captured_at, speed_kmh, processed_storage_path, metadata",
    );
    if (error) throw error;

    const ev = (events && events[0]) as PhotoEventRow | undefined;
    let claim: Awaited<ReturnType<typeof writeClaimablePhoto>> = {
      claimable: false,
      external_code: null,
      reason: "photo_event not found",
    };
    if (ev) {
      try {
        claim = await writeClaimablePhoto(supabase, ev, bucket, storagePath);
      } catch (claimErr) {
        claim = { claimable: false, external_code: null, reason: String(claimErr) };
      }
    }

    return json({ ok: true, claimable: claim.claimable, external_code: claim.external_code });
  } catch (err) {
    if (err instanceof Response) return err;
    return json({ error: String(err) }, 500);
  }
});
