-- F-039 — Ein Ausfalltag wird als Umsatz des Folgetags verbucht
--
-- Projekt: kvpcwlcfgmsmarjtwpsx (geteiltes Projekt)
-- Aufgetreten: 17.08.2026, Imster Bergbahnen
--
-- WAS PASSIERT IST
-- ----------------
-- Der Automat in Imst war 23 Stunden ohne Verbindung. Er hat gepuffert, das hat
-- gehalten: am 17.08. zwischen 08:51 und 09:10 kamen alle 172 Fotos des 16.08.
-- nach. Kein Foto verloren, kein Geld verloren.
--
-- Falsch ist nur die ZUORDNUNG. Diese 172 Fotos wurden auf BEIDEN Tagen
-- gezaehlt: einmal richtig auf dem 16.08., einmal falsch auf dem 17.08. Das
-- Dashboard zeigte deshalb morgens um halb zehn "Umsatz heute 860 EUR" fuer
-- einen Tag, an dem noch kein einziges Foto entstanden war.
--
-- Ursache in vier Schritten:
--   1. handle_new_storage_object setzt captured_at auf die Entstehungszeit des
--      SPEICHEROBJEKTS - das ist der Zeitpunkt des Hochladens.
--   2. rollup_kiosk_photo_sale feuert AFTER INSERT, also sofort. Es prueft
--      source_time_code nur gegen ^[0-9]{8}$. Aus dem Pfad kommt aber
--      '17687440' - acht Ziffern aus dem 16-stelligen Codenamen, kein Datum.
--      Die Pruefung greift, to_date wirft "out of range", der exception-Block
--      setzt still auf null, und es bleibt der Rueckfall auf captured_at.
--   3. Erst DANACH korrigiert liftpic-ingest-commit captured_at und
--      source_time_code. Der Auslöser hat laengst gezaehlt und laeuft nie wieder.
--   4. resync_recent_photo_sales rechnet richtig, korrigiert den Fehler aber
--      nicht: greatest(alt, neu) laesst eine zu hohe Zahl nie wieder sinken.
--
-- Solange Aufnahme- und Hochladetag derselbe sind, ergeben beide Rechnungen
-- dieselbe Zahl - deshalb ist es monatelang nicht aufgefallen.
--
-- WIE AUSFUEHREN
-- --------------
-- Supabase-Oberflaeche -> SQL Editor, Teile einzeln, in dieser Reihenfolge.
-- Teil 0 und Teil 4 aendern nichts und duerfen jederzeit laufen.


-- ===========================================================================
-- TEIL 0 — Vorher ansehen. Aendert nichts.
-- ===========================================================================
-- Zeigt jede Zeile der letzten 30 Tage neben dem, was sie sein muesste.
-- "geisterzeile" heisst: zu diesem Tag existiert kein einziges Foto.

with richtig as (
  select ph.park_id,
         coalesce(ph.camera_code, 'unknown') as camera_code,
         coalesce(
           case when ph.source_time_code ~ '^(0[1-9]|[12][0-9]|3[01])(0[1-9]|1[0-2])[0-9]{4}$'
                then to_date(ph.source_time_code, 'DDMMYYYY') end,
           (substring(ph.storage_path from '/([0-9]{4}-[0-9]{2}-[0-9]{2})/'))::date,
           (coalesce(ph.captured_at, ph.created_at)
              at time zone coalesce(pk.timezone, 'Europe/Vienna'))::date
         ) as business_date,
         count(*) as soll
  from public.photos ph
  join public.parks pk on pk.id = ph.park_id and pk.price_per_photo_cents is not null
  where ph.is_test = false
  group by 1, 2, 3
)
select p.name as park,
       t.business_date,
       t.photos_sold_count               as steht_da,
       coalesce(r.soll, 0)               as muesste_sein,
       coalesce(r.soll, 0) - t.photos_sold_count as differenz,
       (r.soll is null)                  as geisterzeile,
       round((t.photos_sold_count - coalesce(r.soll, 0))
             * p2.price_per_photo_cents / 100.0, 2) as zuviel_ausgewiesen_eur
from public.park_photo_sales_daily t
join public.parks p  on p.id = t.park_id
join public.parks p2 on p2.id = t.park_id
left join richtig r
       on r.park_id = t.park_id
      and r.camera_code = t.camera_code
      and r.business_date = t.business_date
where t.business_date >= current_date - 30
  and coalesce(r.soll, 0) <> t.photos_sold_count
order by t.business_date desc, p.name;


-- ===========================================================================
-- TEIL 1 — Den Auslöser korrigieren, damit es nicht wieder passiert.
-- ===========================================================================
-- Geaendert gegenueber vorher:
--   * Die Datumspruefung ist jetzt STRENG und identisch mit der im Resync.
--     '17687440' faellt damit durch (Monat 68 gibt es nicht), statt to_date
--     zum Werfen zu bringen und still auf die Hochladezeit zurueckzufallen.
--   * NEU als zweite Wahl: das Datumssegment aus dem Speicherpfad
--     (processed/<park>/2026-08-16/...). Das schreibt der Automat aus der
--     echten Aufnahmezeit, es steht schon beim Einfuegen bereit und ueberlebt,
--     dass captured_at zu diesem Zeitpunkt noch die Hochladezeit ist.
--   * Der alte Rueckfall bleibt als dritte Wahl bestehen.
-- Unveraendert: Testfotos zaehlen nicht, Fehler werden geschluckt statt den
-- Upload scheitern zu lassen.

create or replace function public.rollup_kiosk_photo_sale()
returns trigger
language plpgsql
security definer
set search_path to 'public'
as $function$
declare
  v_price_cents integer; v_tz text; v_business_date date; v_file_code integer;
begin
  -- Ein Testfoto ist kein Verkauf.
  if NEW.is_test then return NEW; end if;

  begin
    select price_per_photo_cents, timezone into v_price_cents, v_tz
    from public.parks where id = NEW.park_id;
    if v_price_cents is null then return NEW; end if;

    v_business_date := null;

    -- 1. Wahl: der Zeitcode aus dem Dateinamen, aber nur wenn er wirklich ein
    --    Datum ist. Dieselbe Pruefung wie in resync_recent_photo_sales, damit
    --    Auslöser und naechtliche Neuberechnung nie auseinanderlaufen.
    if NEW.source_time_code ~ '^(0[1-9]|[12][0-9]|3[01])(0[1-9]|1[0-2])[0-9]{4}$' then
      begin
        v_business_date := to_date(NEW.source_time_code, 'DDMMYYYY');
      exception when others then
        v_business_date := null;
      end;
    end if;

    -- 2. Wahl: das Datumssegment im Speicherpfad. Es stammt aus der echten
    --    Aufnahmezeit und steht bereits beim Einfuegen zur Verfuegung - anders
    --    als captured_at, das hier noch die Hochladezeit enthaelt (F-039).
    if v_business_date is null then
      begin
        v_business_date := (substring(NEW.storage_path
                                      from '/([0-9]{4}-[0-9]{2}-[0-9]{2})/'))::date;
      exception when others then
        v_business_date := null;
      end;
    end if;

    -- 3. Wahl: wie bisher. Kann die Hochladezeit sein - dann ist es die beste
    --    verfuegbare Schaetzung, nicht mehr die stille erste Wahl.
    if v_business_date is null then
      v_business_date := (coalesce(NEW.captured_at, NEW.created_at)
        at time zone coalesce(v_tz, 'Europe/Vienna'))::date;
    end if;

    v_file_code := case when NEW.source_file_code ~ '^[0-9]+$'
                        then NEW.source_file_code::integer else null end;

    insert into public.park_photo_sales_daily as psd
      (park_id, camera_code, business_date, photos_sold_count, min_file_code, max_file_code)
    values
      (NEW.park_id, coalesce(NEW.camera_code, 'unknown'), v_business_date, 1, v_file_code, v_file_code)
    on conflict (park_id, camera_code, business_date) do update
      set photos_sold_count = psd.photos_sold_count + 1,
          min_file_code = least(psd.min_file_code, excluded.min_file_code),
          max_file_code = greatest(psd.max_file_code, excluded.max_file_code),
          updated_at = now();
  exception when others then
    raise warning 'rollup_kiosk_photo_sale failed for photo %: %', NEW.id, sqlerrm;
  end;
  return NEW;
end;
$function$;


-- ===========================================================================
-- TEIL 2 — Den Resync korrigieren, damit er auch nach unten korrigieren darf.
-- ===========================================================================
-- Geaendert gegenueber vorher:
--   * greatest(alt, neu) -> neu. Das war der Grund, warum eine einmal zu hoch
--     eingetragene Zahl fuer immer stehen blieb. Der Resync rechnet aus der
--     Fototabelle, er ist die verlaessliche Quelle - er darf sie setzen.
--   * Dasselbe Datumssegment als zweite Wahl wie im Auslöser.

create or replace function public.resync_recent_photo_sales()
returns void
language plpgsql
security definer
set search_path to 'public'
as $function$
begin
  insert into public.park_photo_sales_daily as t
    (park_id, camera_code, business_date, photos_sold_count)
  select park_id, camera_code, business_date, sold from (
    select ph.park_id,
           coalesce(ph.camera_code, 'unknown') as camera_code,
           coalesce(
             case when ph.source_time_code ~ '^(0[1-9]|[12][0-9]|3[01])(0[1-9]|1[0-2])[0-9]{4}$'
                  then to_date(ph.source_time_code, 'DDMMYYYY') end,
             (substring(ph.storage_path from '/([0-9]{4}-[0-9]{2}-[0-9]{2})/'))::date,
             (coalesce(ph.captured_at, ph.created_at)
                at time zone coalesce(pk.timezone, 'Europe/Vienna'))::date
           ) as business_date,
           count(*) as sold
    from public.photos ph
    join public.parks pk on pk.id = ph.park_id and pk.price_per_photo_cents is not null
    where ph.is_test = false
    group by 1, 2, 3
  ) x
  where business_date >= (current_date - interval '10 days')
  on conflict (park_id, camera_code, business_date) do update
    set photos_sold_count = excluded.photos_sold_count,
        updated_at = now();
end;
$function$;


-- ===========================================================================
-- TEIL 3 — Einmalig aufraeumen.
-- ===========================================================================
-- Erst die Geisterzeilen loeschen (Tage, zu denen kein einziges Foto existiert),
-- dann den Resync die verbliebenen Zahlen richtigstellen lassen.
--
-- Das Fenster ist bewusst auf 30 Tage begrenzt. Aeltere Zeilen bleiben
-- unangetastet - Teil 0 zeigt, ob dort ueberhaupt etwas abweicht.

with richtig as (
  select ph.park_id,
         coalesce(ph.camera_code, 'unknown') as camera_code,
         coalesce(
           case when ph.source_time_code ~ '^(0[1-9]|[12][0-9]|3[01])(0[1-9]|1[0-2])[0-9]{4}$'
                then to_date(ph.source_time_code, 'DDMMYYYY') end,
           (substring(ph.storage_path from '/([0-9]{4}-[0-9]{2}-[0-9]{2})/'))::date,
           (coalesce(ph.captured_at, ph.created_at)
              at time zone coalesce(pk.timezone, 'Europe/Vienna'))::date
         ) as business_date
  from public.photos ph
  join public.parks pk on pk.id = ph.park_id and pk.price_per_photo_cents is not null
  where ph.is_test = false
  group by 1, 2, 3
)
delete from public.park_photo_sales_daily t
where t.business_date >= current_date - 30
  and not exists (
    select 1 from richtig r
    where r.park_id = t.park_id
      and r.camera_code = t.camera_code
      and r.business_date = t.business_date
  );

-- Der Resync deckt zehn Tage ab und setzt die Zahlen jetzt exakt.
select public.resync_recent_photo_sales();


-- ===========================================================================
-- TEIL 4 — Nachher pruefen. Aendert nichts.
-- ===========================================================================
-- Erwartung: Teil 0 liefert keine Zeile mehr. Und fuer Imst muss stehen:
--   16.08. = 172   (der echte Betriebstag, nachgeliefert)
--   17.08. = die Fotos, die heute wirklich entstanden sind
--            (zum Zeitpunkt der Behebung: keine)

select p.name as park,
       s.business_date,
       s.photos_sold_count,
       round(s.photos_sold_count * p.price_per_photo_cents / 100.0, 2) as umsatz_eur,
       s.updated_at at time zone coalesce(p.timezone, 'Europe/Vienna') as geschrieben
from public.park_photo_sales_daily s
join public.parks p on p.id = s.park_id
where s.business_date >= current_date - 5
order by s.business_date desc, p.name;
