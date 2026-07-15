import { json, requireMachineAuth } from "../_shared/auth.ts";
import { serviceClient } from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  try {
    const auth = await requireMachineAuth(req);
    const body = await req.json();
    const metadata = body.metadata ?? {};
    const bucket = Deno.env.get("LIFTPIC_BUCKET") ?? "test";
    const parkSlug = metadata.park_slug ?? "unknown-park";
    const legacyFilename = metadata.legacy_filename;
    const capturedAt = metadata.captured_at ?? new Date().toISOString();
    const eventKey = metadata.event_key ?? `${String(capturedAt).slice(0, 10)}|${metadata.capture_id}`;
    if (!legacyFilename) {
      return json({ error: "metadata.legacy_filename is required" }, 400);
    }

    const date = String(capturedAt).slice(0, 10);
    const storagePath = `processed/${parkSlug}/${date}/${legacyFilename}`;
    const supabase = serviceClient();

    const { error: upsertError } = await supabase.from("photo_events").upsert({
      park_id: auth.parkId,
      park_slug: parkSlug,
      machine_id: auth.machineId,
      event_key: eventKey,
      camera_code: metadata.camera_code ?? null,
      capture_id: metadata.capture_id,
      legacy_filename: legacyFilename,
      legacy_code: metadata.legacy_code,
      time_code: metadata.time_code,
      file_code: metadata.file_code,
      raw_local_name: metadata.raw_path,
      captured_at: capturedAt,
      speed_kmh: metadata.speed_kmh,
      speed_status: metadata.speed_status ?? "missing",
      upload_status: "uploading",
      checksum_sha256: metadata.checksum_sha256,
      processed_storage_path: storagePath,
      metadata,
    }, { onConflict: "machine_id,event_key" });
    if (upsertError) throw upsertError;

    const { data, error } = await supabase.storage
      .from(bucket)
      .createSignedUploadUrl(storagePath, { upsert: true });
    if (error) throw error;

    return json({
      upload: {
        bucket,
        storage_path: storagePath,
        signed_url: data.signedUrl ?? data.signedURL,
        token: data.token,
      },
    });
  } catch (err) {
    if (err instanceof Response) return err;
    return json({ error: String(err) }, 500);
  }
});
