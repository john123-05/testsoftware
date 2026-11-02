import { json, requireMachineAuth } from "../_shared/auth.ts";
import { serviceClient } from "../_shared/supabase.ts";
import {onlineStream,ONLINE_BUCKET} from '../_shared/onlinePhotos.ts';

/**
 * Die Kundennummer aus dem 16-stelligen Codenamen zurueckrechnen.
 *
 * Dieselbe Rechnung wie `parse_source_customer_code` in der Datenbank:
 * Positionen 1, 9, 4, 10 (1-basiert).
 */
function customerCodeFromName(filename: string): string | null {
  const core = filename.replace(/\.[^.]+$/, "");
  if (!/^\d{16}$/.test(core)) return null;
  return core[0] + core[8] + core[3] + core[9];
}

Deno.serve(async (req) => {
  try {
    const auth = await requireMachineAuth(req);
    const body = await req.json();
    const metadata = body.metadata ?? {};
    let bucket = Deno.env.get("LIFTPIC_BUCKET") ?? "test";
    const parkSlug = metadata.park_slug ?? "unknown-park";
    const legacyFilename = metadata.legacy_filename;
    const capturedAt = metadata.captured_at ?? new Date().toISOString();
    const eventKey = metadata.event_key ?? `${String(capturedAt).slice(0, 10)}|${metadata.capture_id}`;
    if (!legacyFilename) {
      return json({ error: "metadata.legacy_filename is required" }, 400);
    }

    const isTest = metadata.is_test === true;
    const supabase = serviceClient();

    // Schutz fuer Testfotos.
    //
    // Die Fotozeile entsteht nicht hier, sondern im Datenbank-Trigger - und der
    // leitet den Park aus der Kundennummer IM DATEINAMEN ab. Findet er sie
    // nicht in `park_cameras`, faellt er auf die Zuordnung Bucket -> Park
    // zurueck, und der gemeinsame Bucket `test` zeigt auf einen fremden Park.
    //
    // Genau so ist am 15.08.2026 ein Testfoto des Testrechners in Imsts Daten
    // gelandet: der Automat schreibt die Kundennummer des Verkaufsprogramms
    // (1234) in den Namen, registriert war aber nur 7623.
    //
    // Hier ist der Park durch die Anmeldung bekannt. Also wird geprueft, ob der
    // Name auch wirklich dorthin zeigt - und der Upload sonst abgelehnt.
    // Bewusst nur fuer Testfotos: echte Aufnahmen verhalten sich unveraendert.
    if (isTest) {
      const code = customerCodeFromName(String(legacyFilename));
      if (!code) {
        return json({
          error: `Testfoto abgelehnt: '${legacyFilename}' ist kein 16-stelliger Codename.`,
        }, 400);
      }
      const { data: cams } = await supabase
        .from("park_cameras")
        .select("park_id")
        .eq("customer_code", code)
        .eq("is_active", true);
      const parks = new Set((cams ?? []).map((c: { park_id: string }) => c.park_id));
      if (parks.size !== 1 || !parks.has(auth.parkId)) {
        return json({
          error: `Testfoto abgelehnt: Kundennummer ${code} ist fuer diesen Park ` +
            `nicht registriert - das Foto wuerde einem fremden Park zugeordnet. ` +
            `Bitte ${code} in park_cameras eintragen.`,
        }, 409);
      }
    }

    const date = String(capturedAt).slice(0, 10);
    // Test photos live under .../testfoto/... - handle_new_storage_object spots
    // that segment and marks the row is_test, so it never counts as a sale.
    // Without the flag the path is byte-identical to before, which is what
    // every existing machine keeps producing.
    const testSegment = isTest ? "testfoto/" : "";
    let storagePath = `processed/${parkSlug}/${testSegment}${date}/${legacyFilename}`;
    const online=await onlineStream(auth,metadata.camera_code??'');
    if(online){
      if(!/^\d{16}\.jpg$/i.test(String(legacyFilename))||customerCodeFromName(legacyFilename)!==online.legacy_customer_code||!/^[0-9a-f]{64}$/.test(metadata.checksum_sha256??'')||!/^\d{4}-\d{2}-\d{2}$/.test(date)||(online.parks as any)?.slug!==parkSlug)return json({error:'Invalid private online photo'},403);
      bucket=ONLINE_BUCKET;
      storagePath=`${auth.parkId}/${metadata.camera_code}/${testSegment}${date}/${metadata.checksum_sha256}.jpg`;
      metadata.upload_bucket=ONLINE_BUCKET;
      // Once committed, never issue another upload URL that can overwrite this original.
      const previous=await supabase.from('online_photo_assets').select('checksum_sha256,storage_path').eq('park_id',auth.parkId).eq('claim_code',String(legacyFilename).slice(0,16)).maybeSingle();
      if(previous.error)throw previous.error;
      if(previous.data&&!isTest){
        if(previous.data.checksum_sha256!==metadata.checksum_sha256||previous.data.storage_path!==storagePath)return json({error:'Photo code collision'},409);
        return json({already_uploaded:true,upload:{bucket,storage_path:storagePath}});
      }
    }

    if(auth.secured){
      const {data:configs,error:configError}=await supabase.from('liftpic_machine_configs').select('camera_code,legacy_customer_code,shadow_mode,mode,parks(slug)').eq('machine_id',auth.machineId).eq('park_id',auth.parkId).eq('is_active',true);
      const stream=configs?.find(c=>c.camera_code===metadata.camera_code&&c.legacy_customer_code===(metadata.customer_code??customerCodeFromName(String(legacyFilename))));
      if(configError||!stream||customerCodeFromName(String(legacyFilename))!==stream.legacy_customer_code||(!isTest&&(stream.shadow_mode||stream.mode==='count_only'))||(stream.parks as any)?.slug!==parkSlug||!/^\d{16}\.jpg$/i.test(legacyFilename))return json({error:'Unapproved camera, filename, target or upload mode'},403);
      metadata.customer_code=stream.legacy_customer_code;
    }
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
        signed_url: data.signedUrl,
        token: data.token,
      },
    });
  } catch (err) {
    if (err instanceof Response) return err;
    return json({ error: String(err) }, 500);
  }
});
