import { json, requireMachineAuth } from "../_shared/auth.ts";
import { serviceClient } from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  try {
    const auth = await requireMachineAuth(req);
    const body = await req.json();
    const supabase = serviceClient();
    const { error } = await supabase.from("machine_status").upsert({
      machine_id: auth.machineId,
      park_id: auth.parkId,
      park_slug: body.park_slug ?? "unknown-park",
      app_version: body.app_version ?? null,
      camera_code: body.camera_code ?? null,
      last_seen_at: new Date().toISOString(),
      queue_count: body.queue_count ?? 0,
      disk_free_mb: body.disk_free_mb ?? null,
      camera_status: body.camera_status ?? null,
      paper_status: body.paper_status ?? null,
      paper_remaining: body.paper_remaining ?? null,
      photos_taken_today: body.photos_taken_today ?? 0,
      photos_sold_today: body.photos_sold_today ?? 0,
      photo_conversion_today: body.photo_conversion_today ?? null,
      last_error: body.last_error ?? null,
      payload: body,
    }, { onConflict: "machine_id" });
    if (error) throw error;

    await supabase
      .from("liftpic_machine_configs")
      .update({
        last_seen_at: new Date().toISOString(),
        last_status: body,
      })
      .eq("machine_id", auth.machineId)
      .eq("camera_code", body.camera_code ?? auth.cameraCode ?? "default");

    const rideRollups: Record<string, unknown>[] =
      Array.isArray(body.ride_rollups) ? body.ride_rollups : [];
    if (rideRollups.length > 0) {
      const rows = rideRollups
        .filter((item) => item && item.business_date)
        .map((item) => ({
          park_id: auth.parkId,
          park_slug: item.park_slug ?? body.park_slug ?? "unknown-park",
          machine_id: auth.machineId,
          camera_code: item.camera_code ?? body.camera_code ?? "default",
          business_date: item.business_date,
          photos_taken_count: item.photos_taken_count ?? 0,
          photos_sold_count: item.photos_sold_count ?? 0,
          conversion_rate: item.conversion_rate ?? null,
          first_capture_at: item.first_capture_at ?? null,
          last_capture_at: item.last_capture_at ?? null,
          last_sale_at: item.last_sale_at ?? null,
          speed_ok_count: item.speed_ok_count ?? 0,
          last_seen_at: new Date().toISOString(),
          payload: item,
        }));

      if (rows.length > 0) {
        const { error: rollupError } = await supabase
          .from("park_photo_ride_daily")
          .upsert(rows, { onConflict: "machine_id,camera_code,business_date" });
        if (rollupError) throw rollupError;
      }
    }

    // Log a throttled ride snapshot (the running daily ride count with a
    // timestamp) so the dashboard can chart rides-per-hour by diffing
    // consecutive snapshots - no PC/agent change needed. Never fail the
    // heartbeat over this.
    try {
      const businessDate =
        (rideRollups as Array<{ business_date?: unknown }>)
          .map((item) => item?.business_date)
          .filter((d): d is string => typeof d === "string")
          .sort()
          .pop() ?? new Date().toISOString().slice(0, 10);

      const { data: lastSnap } = await supabase
        .from("machine_ride_snapshots")
        .select("captured_at")
        .eq("machine_id", auth.machineId)
        .order("captured_at", { ascending: false })
        .limit(1)
        .maybeSingle();
      const lastMs = lastSnap?.captured_at ? new Date(lastSnap.captured_at as string).getTime() : 0;

      if (Date.now() - lastMs > 4 * 60 * 1000) {
        await supabase.from("machine_ride_snapshots").insert({
          park_id: auth.parkId,
          machine_id: auth.machineId,
          business_date: businessDate,
          rides_today: Number(body.photos_taken_today ?? 0),
          photos_sold_today: Number(body.photos_sold_today ?? 0),
          // Cumulative physical print counter (PrintCount.txt). Each print is a
          // real sale, so diffing this per day gives the true sold count -
          // immune to a polluted qrcode folder / upload queue.
          paper_printed: body.paper_printed != null ? Number(body.paper_printed) : null,
        });
      }
    } catch (_snapErr) {
      // snapshot logging must never break the heartbeat
    }

    // Health notes the machine buffered while it could not reach us (connection
    // lost/restored, a tool that started failing). last_status only ever holds
    // the CURRENT picture and is overwritten every minute, so without this the
    // record of what happened during an outage would be lost the moment it
    // ended. Ignored silently if the table does not exist yet, and wrapped so a
    // problem here can never cost us a heartbeat.
    try {
      const buffered = Array.isArray(body.buffered_events) ? body.buffered_events : [];
      if (buffered.length > 0) {
        const rows = buffered
          .filter((item: Record<string, unknown>) => item && item.occurred_at && item.summary)
          .slice(0, 200)
          .map((item: Record<string, unknown>) => ({
            park_id: auth.parkId,
            machine_id: auth.machineId,
            occurred_at: item.occurred_at,
            kind: String(item.kind ?? "system").slice(0, 40),
            severity: String(item.severity ?? "info").slice(0, 20),
            summary: String(item.summary).slice(0, 500),
            detail: item.detail != null ? String(item.detail).slice(0, 2000) : null,
          }));

        if (rows.length > 0) {
          // Matches the unique index (machine_id, occurred_at, summary):
          // a redelivery after an interrupted acknowledgement must not produce
          // the same entry twice.
          await supabase
            .from("liftpic_machine_health_events")
            .upsert(rows, {
              onConflict: "machine_id,occurred_at,summary",
              ignoreDuplicates: true,
            });
        }
      }
    } catch (_eventErr) {
      // buffered health notes must never break the heartbeat
    }

    // Zahlungszuordnung je Kauf. Der Agent wertet sein Münz- und
    // Karten-Protokoll aus (Statistic.txt-Kennzeichen 2=Karte / 1=Bar plus
    // hobex-HDL für Betrag/Kartenmarke/Beleg) und schickt fertige Verkaufs-
    // zeilen mit; wir schreiben sie nach machine_sale_payments. Der Herzschlag
    // darf daran NIE scheitern. Dedup gegen Vorhandenes: Kartenzeilen über
    // receipt_no, Bar/unbekannt über (sold_local, bild_nr, method) - der Agent
    // schickt normalerweise nur Neues, das hier ist die Absicherung gegen
    // Wiederholung nach abgebrochener Bestätigung.
    try {
      const sales: Record<string, unknown>[] =
        Array.isArray(body.sale_payments) ? body.sale_payments : [];
      if (sales.length > 0) {
        const rows = sales
          .filter((s: Record<string, unknown>) =>
            s && s.sold_local &&
            ["karte", "bar", "unbekannt"].includes(String(s.method)))
          .slice(0, 1000)
          .map((s: Record<string, unknown>) => ({
            park_id: auth.parkId,
            machine_id: auth.machineId,
            sold_local: String(s.sold_local),
            // Der Agent kennt seine Zeitzone und schickt sold_at als ISO mit
            // Offset. Fehlt es, deutet Postgres sold_local in der DB-Zeitzone
            // (UTC) - grobe Notlösung, der Agent soll sold_at immer mitgeben.
            sold_at: s.sold_at ? String(s.sold_at) : String(s.sold_local),
            bild_nr: s.bild_nr != null ? String(s.bild_nr) : null,
            print_count: s.print_count != null ? Number(s.print_count) : null,
            method: String(s.method),
            method_source: String(s.method_source ?? "automat_flag"),
            amount_cents: s.amount_cents != null ? Number(s.amount_cents) : null,
            card_scheme: s.card_scheme != null ? String(s.card_scheme) : null,
            receipt_no: s.receipt_no != null ? String(s.receipt_no) : null,
            auth_code: s.auth_code != null ? String(s.auth_code) : null,
            pan_masked: s.pan_masked != null ? String(s.pan_masked) : null,
            match_delta_s: s.match_delta_s != null ? Number(s.match_delta_s) : null,
            source_file: s.source_file != null ? String(s.source_file) : "agent",
          }));

      const withReceipt = rows.filter((r) => r.receipt_no);
      const withoutReceipt = rows.filter((r) => !r.receipt_no);
      const toInsert: typeof rows = [];

      if (withReceipt.length > 0) {
        const { data: existing } = await supabase
          .from("machine_sale_payments")
          .select("receipt_no")
          .eq("machine_id", auth.machineId)
          .in("receipt_no", [...new Set(withReceipt.map((r) => r.receipt_no as string))]);
        const seen = new Set((existing ?? []).map((e: { receipt_no: string }) => e.receipt_no));
        for (const r of withReceipt) if (!seen.has(r.receipt_no as string)) toInsert.push(r);
      }
      if (withoutReceipt.length > 0) {
        const locals = [...new Set(withoutReceipt.map((r) => r.sold_local))];
        const { data: existing } = await supabase
          .from("machine_sale_payments")
          .select("sold_local, bild_nr, method")
          .eq("machine_id", auth.machineId)
          .is("receipt_no", null)
          .in("sold_local", locals);
        const seen = new Set(
          (existing ?? []).map(
            (e: Record<string, unknown>) => `${e.sold_local}|${e.bild_nr ?? ""}|${e.method}`,
          ),
        );
        for (const r of withoutReceipt) {
          const k = `${r.sold_local}|${r.bild_nr ?? ""}|${r.method}`;
          if (!seen.has(k)) toInsert.push(r);
        }
      }

      if (toInsert.length > 0) {
        await supabase.from("machine_sale_payments").insert(toInsert);
      }
      }
    } catch (_payErr) {
      // Zahlungszeilen dürfen den Herzschlag nie brechen
    }

    return json({ ok: true });
  } catch (err) {
    if (err instanceof Response) return err;
    return json({ error: String(err) }, 500);
  }
});
