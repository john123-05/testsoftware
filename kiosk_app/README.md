# Liftpictures Kiosk

Neues Verkaufsprogramm für Fotoautomaten (Nachfolger von PhotoViewerFacebook).
React + TypeScript + Vite, läuft offline. Im Automaten im Programm **Liftpictures Display** (WebView2),
im Browser als **Demo mit Simulator** (Münzen, Karte, Drucker, Gesicht per Klick).

```
npm install
npm run dev        # http://localhost:5193 (Demo + Simulator rechts)
npm run build      # dist/ fuer Liftpictures Display
```

Demo-Adresse mit Parametern: `?screen=gallery|cart|cash|…` (direkt springen), `&frame=portrait|landscape`,
`&edition=complete|card_cash|card|cash|digital`, `&theme=alpine|night|sunset|clean`, `&tier=low|mid|high`,
`&lang=de`, `&nopanel` (ohne Simulator).

## Aufbau
- `config.ts` – Einstellungen, **Versionen** (Komplett, Karte + Bargeld, Nur Karte, Nur Bargeld, Nur digital), Farbwelten.
- `store.tsx` – Ablauf: Suche → Foto → Format → Warenkorb → Zahlart → Bezahlen → Abschluss.
- `hardware.ts` – Geräte: `SimHardware` (Demo) und `HostHardware` (Nachrichten an Liftpictures Display:
  `{type:'hw', id, method, args}` → `{type:'hw-result', id, result}`, Ereignisse `{type:'hw-event', event, value}`).
- `data.ts` – Fotos/Einstellungen: der Agent schreibt `data.js` → `window.__kiosk({licensed, reason, config, photos})`.
- `perf.ts` – Leistungsstufe des PCs (low/mid/high) misst Bildrate, Kerne, Speicher; stuft im Betrieb herunter.
- `i18n.ts` – Gästetexte EN/DE/FR/ES/IT/NL.

## Stand / nächste Schritte
1. ✅ Oberfläche, Abläufe, Simulator, Versionen, Sprachen, Hoch-/Querformat, Leistungsstufen, Hilfe, Leerlauf.
2. ⏳ Liftpictures Display `--kiosk`: App ausliefern, Fotos + Vorschaubilder, Gerätebrücke
   (Kartenterminal über easyzvt.exe wie bisher, NRI-Münzprüfer über PaymentManager, Drucker, FaceAiSharp).
3. ⏳ Agent: `data.js` (Fotos, Codes, Einstellungen) + Lizenz (wie Presentation: `kiosk_enabled`, gültig bis).
4. ⏳ CRM/Dashboard: Einstellungen und Gestaltung des Verkaufsprogramms je Automat.
