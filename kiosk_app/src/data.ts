/// <reference types="vite/client" />
// Fotos und Einstellungen.
// Im Automaten schreibt der Agent (Liftpic Sync) data.js: window.__kiosk({licensed, reason, base, config, photos}).
// Liftpictures Display liefert sie unter https://kiosk-media.liftpictures/ aus, dazu die Fotos
// (photo/<datei>) und verkleinerte Vorschaubilder (thumb/<datei>), die es selbst erzeugt und zwischenspeichert.
// Die App laedt data.js alle 2 Sekunden neu - neue Fotos stehen sofort zur Auswahl, auch ohne Internet.
// Im Browser/Demo: echte lokale Demo-Fotos oder neutrale Platzhalter.
import { useEffect, useRef, useState } from 'react';

export type Photo = { key: string; src: string; thumb?: string; file?: string; number: string; ts: number; code?: string; url?: string };
export type KioskData = {
  licensed: boolean; reason?: string | null; valid_until?: string | null; machine_id?: string;
  /** Was der Agent weiss (Links zur Kaufseite, Logo) - darunter liegen die Vorgaben, darueber das CRM. */
  base?: unknown; config?: unknown; photos: Photo[];
  /** Am Automaten erst wahr, wenn data.js vom Agenten wirklich da war. */
  loaded?: boolean;
};

/** Ein Betriebstag: die letzten 20 Stunden (Parks ueber Mitternacht, Demo am Morgen). */
export const DAY_SECONDS = 20 * 3600;
export const inDay = (p: Photo, now = Date.now() / 1000) => p.ts >= now - DAY_SECONDS;

export const MEDIA = (window as unknown as { __KIOSK_MEDIA?: string }).__KIOSK_MEDIA ?? 'https://kiosk-media.liftpictures/';
const DATA_URL = `${MEDIA}data.js`;
/** Ohne data.js so lange kommt der Hinweis "Bitte Personal rufen" (Agent laeuft nicht). */
const NO_DATA_MS = 30_000;

/** Pfade aus data.js (z. B. "park-logo?v=1") zeigen auf den Medien-Server. */
export function mediaUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  return /^(https?:|data:)/.test(path) ? path : MEDIA + path.replace(/^\/+/, '');
}

function withMedia(p: Photo): Photo {
  if (!p.file || p.src) return p;
  const f = encodeURIComponent(p.file);
  return { ...p, src: `${MEDIA}photo/${f}`, thumb: `${MEDIA}thumb/${f}` };
}

function withLogo(base: unknown): unknown {
  const b = base as { theme?: { logo?: string | null } } | undefined;
  if (!b?.theme?.logo) return base;
  return { ...b, theme: { ...b.theme, logo: mediaUrl(b.theme.logo) } };
}

function rng(seed: number) {
  let s = seed >>> 0 || 1;
  return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
}
declare const __DEMO_PHOTOS__: string[];

const demoPhotos = __DEMO_PHOTOS__;
const placeholderCache = new Map<string, string>();

function placeholder(p: Photo): string {
  const cached = placeholderCache.get(p.key);
  if (cached) return cached;
  const number = p.number.replace(/[^0-9]/g, '');
  const time = new Date(p.ts * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400">
    <rect width="600" height="400" fill="#e3e7e6"/>
    <g fill="none" stroke="#576560" stroke-width="5" stroke-linejoin="round">
      <path d="M251 147h24l10-14h30l10 14h24v61h-98z"/>
      <circle cx="300" cy="177" r="17"/>
    </g>
    <text x="300" y="253" fill="#37423e" text-anchor="middle" font-family="sans-serif" font-size="24">${number} · ${time}</text>
  </svg>`;
  const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  if (placeholderCache.size > 500) placeholderCache.clear();
  placeholderCache.set(p.key, url);
  return url;
}

export const photoSrc = (p: Photo) => p.thumb || p.src || placeholder(p);
export const photoFull = (p: Photo) => p.src || placeholder(p);

function sample(n: number, ts: number): Photo {
  const number = String(n % 10000).padStart(4, '0');
  return { key: `demo-${n}`, src: demoPhotos.length ? import.meta.env.BASE_URL + demoPhotos[n % demoPhotos.length] : '', number, ts, code: `4456${number}${String(ts).slice(-8)}` };
}

/** Rund 250 Beispielfotos der letzten 6,5 Stunden, neueste zuerst. */
export function samplePhotos(now = Date.now()): Photo[] {
  const r = rng(7);
  const out: Photo[] = [];
  let t = now - 6.5 * 3600 * 1000;
  let n = 4100;
  for (;;) {
    t += (40 + r() * 110) * 1000;
    if (t > now - 20_000) break;
    out.push(sample(++n, Math.floor(t / 1000)));
  }
  return out.reverse();
}

export function useKioskData(sim: boolean) {
  const [data, setData] = useState<KioskData>(() => (sim ? { licensed: true, loaded: true, photos: samplePhotos() } : { licensed: true, loaded: false, photos: [] }));
  const last = useRef('');

  useEffect(() => {
    if (sim) {
      // Demo: alle 75 Sekunden faehrt jemand.
      const id = window.setInterval(() => setData((d) => ({ ...d, photos: [sample(Number(d.photos[0]?.number ?? 4100) + 1, Math.floor(Date.now() / 1000)), ...d.photos] })), 75_000);
      return () => window.clearInterval(id);
    }
    let loadedAt = 0;
    const started = Date.now();
    (window as unknown as { __kiosk?: (d: KioskData) => void }).__kiosk = (d: KioskData) => {
      loadedAt = Date.now();
      const sig = JSON.stringify([d.licensed, d.reason, d.valid_until, d.base, d.config, d.photos?.length, d.photos?.[0]?.key]);
      if (sig === last.current) return;
      last.current = sig;
      setData({ ...d, loaded: true, base: withLogo(d.base), photos: (d.photos ?? []).map(withMedia).sort((a, b) => b.ts - a.ts) });
    };
    const watchdog = window.setInterval(() => {
      // Kommt lange nichts (Agent aus), lieber einen Hinweis zeigen als einen leeren Automaten.
      if (!loadedAt && Date.now() - started > NO_DATA_MS && last.current !== 'no_data') {
        last.current = 'no_data';
        setData({ licensed: false, reason: 'no_data', photos: [] });
      }
    }, 5000);
    let current: HTMLScriptElement | null = null;
    const load = () => {
      const s = document.createElement('script');
      s.src = `${DATA_URL}?t=${Date.now()}`;
      s.onload = s.onerror = () => { current?.remove(); current = s; };
      document.head.appendChild(s);
    };
    load();
    const id = window.setInterval(load, 2000);
    return () => { window.clearInterval(id); window.clearInterval(watchdog); };
  }, [sim]);

  const addSample = () => setData((d) => ({ ...d, photos: [sample(Number(d.photos[0]?.number ?? 4100) + 1, Math.floor(Date.now() / 1000)), ...d.photos] }));
  return { ...data, addSample };
}
