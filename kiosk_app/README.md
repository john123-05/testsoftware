# Liftpictures Kiosk

Neues Verkaufsprogramm für Fotoautomaten (Nachfolger von PhotoViewerFacebook).
React + TypeScript + Vite, läuft offline. Im Automaten im Programm **Liftpictures Display** (WebView2),
im Browser als **Demo mit Simulator** (Münzen, Karte, Drucker, Gesicht per Klick).

```
npm install
npm run dev        # http://localhost:5193 (Demo + Simulator rechts)
npm run build      # dist/ fuer Liftpictures Display
```

Demo-Adresse mit Parametern: `?screen=attract|gallery|scan|print_home|cart|cash|…` (direkt springen), `&frame=portrait|landscape`,
`&edition=complete|card_cash|card|cash|digital`, `&theme=clean|dark`, `&tier=low|mid|high`,
`&lang=de`, `&nopanel` (ohne Simulator).

Für echte Beispielfotos im Simulator JPEG-Dateien unter `kiosk_app/public/demo/` ablegen
und den Simulator neu starten. Ohne Beispiele zeigt die Galerie neutrale Platzhalter.

## Aufbau
- `config.ts` – Einstellungen, **Versionen** (Komplett, Karte + Bargeld, Nur Karte, Nur Bargeld, Nur digital), Farbwelten.
  Ebenen: Vorgaben < was der Agent weiß (`base`: Links zur Kaufseite, Logo) < CRM (`config`).
- `store.tsx` – Ablauf: Suche → Foto → Format → Warenkorb → Zahlart → Bezahlen → Abschluss; jeder Verkauf geht als
  `SaleRecord` an das Programm (`hw.sale`).
- `hardware.ts` – Geräte: `SimHardware` (Demo) und `HostHardware` (Nachrichten an Liftpictures Display:
  `{type:'hw', id, method, args}` → `{type:'hw-result', id, result}`, Ereignisse `{type:'hw-event', event, value}`).
  Methoden: status, configure, cashEnable/Disable/Payout, cardPay/Cancel, print, pickup, faceSearch, sale, exit.
- `data.ts` – Fotos/Einstellungen: der Agent schreibt `C:\liftpic\kiosk-data\data.js` →
  `window.__kiosk({licensed, reason, valid_until, base, config, photos})`; Fotos kommen als
  `https://kiosk-media.liftpictures/thumb|photo/<datei>` (480/2048 px, das Programm verkleinert und speichert zwischen).
- `vouchers.ts` – Gutscheine/Tagespass, offline prüfbar (HMAC mit Schlüssel aus dem CRM).
- `perf.ts` – Leistungsstufe des PCs (low/mid/high) misst Bildrate, Kerne, Speicher; stuft im Betrieb herunter.
- `i18n.ts` – Gästetexte EN/DE/FR/ES/IT/NL.
- Vorschau für CRM/Dashboard: `?preview&nopanel&screen=…` – Einstellungen per `postMessage({type:'kiosk-preview', config})`.
  Übernehmen: `python3 scripts/kiosk_ins_crm.py <repo> [ts-ordner]`.

## Im Automaten
- Programm: `LiftpicturesDisplay.exe --kiosk` (Ordner `kiosk\` daneben = diese App). Einrichten:
  `scripts\display_einrichten.ps1 -Kiosk` (Verknüpfungen), `-KioskAutostart` (auch Autostart).
  Startet nicht, solange das alte Verkaufsprogramm läuft.
- Geräte wie im alten Programm (Werte aus dessen `Settings.xml`, vom Agenten in `host.json`):
  Kartenterminal über easyzvt.exe + Registry (Betrag/Ergebnis), NRI-Münzgerät über `PhotoViewerLib.dll`/
  `PaymentManager.dll` aus `samuel_neu` (Protokoll bleibt in `samuel_neu\Log`), Drucker über den Windows-Treiber
  (Foto, QR, Logo, Datum an den Positionen der Settings.xml), Gesichtssuche über `FaceAiSharpClient.exe`.
- Schreibt wie das alte Programm `Statistic.txt` (Zahlart-Feld 2 = Karte, 1 = bar), `PrintCount.txt`, `CoinStats.txt`
  und kopiert verkaufte Fotos in den Verkauft-Ordner (`qrcode`) – Hochladen, Zahlungen und Dashboard laufen unverändert.
  Neu: `kiosk-data\sales\JJJJ-MM-TT.jsonl`, `alive.json`, `logs\display-*.log`.
- Lizenz: CRM → Kunde → Funktionen → „Verkaufsprogramm & Lizenz“ (an/aus, gültig bis, was der Kunde selbst ändern darf).

## Stand
1. ✅ Oberfläche, Abläufe, Simulator, Versionen, Sprachen, Hoch-/Querformat, Leistungsstufen, Hilfe, Leerlauf.
2. ✅ Liftpictures Display `--kiosk` mit Gerätebrücke (Version 0.7.0, gebaut in CI) – **noch nicht an echter Hardware
   getestet**: Kartenterminal, Münzgerät, Drucker und Gesichtssuche einmal vor Ort mit Tom prüfen.
3. ✅ Agent: `data.js`, `host.json`, Lizenz, Verkäufe im Herzschlag (0.7.0).
4. ✅ CRM (Freischaltung + Baukasten mit Live-Vorschau, Gutscheine) und Dashboard (Kunde ändert Freigegebenes).
5. ⏳ Bar/Karte an Parks mit Online-Shop: Download-QR braucht eine signierte Freischaltung im Shop (heute: Handy-Kauf).

## Fotoabholung und Lieferung

- Im CRM pro Automat **Code scannen** freigeben. Der Scanner akzeptiert Gutscheine,
  Bildcodes und QR-Codes für Online-Abholungen. Für Abholungen braucht der gepaarte
  Automat Internet, einen Drucker und die Originale im aktuellen Fotobestand.
- Die Claim-Seite zeigt den Abholcode für berechtigte Gäste, sobald der Park einen
  passenden Automaten anbietet. Die Datenbank reserviert den Code vor dem Druck.
  Scheitert der Druck nach der Reservierung, prüft das Personal den Auftrag.
- **Nach Hause liefern** erscheint bei einer HTTPS-Adresse mit `{code}` im CRM.
  Der QR-Code führt zum Shop auf dem Handy. Der Plose-Shop ist im Testbetrieb.
