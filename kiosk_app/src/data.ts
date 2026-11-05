// Fotos und Einstellungen.
// Im Automaten schreibt der Agent (Liftpic Sync) data.js: window.__kiosk({licensed, reason, base, config, photos}).
// Liftpictures Display liefert sie unter https://kiosk-media.liftpictures/ aus, dazu die Fotos
// (photo/<datei>) und verkleinerte Vorschaubilder (thumb/<datei>), die es selbst erzeugt und zwischenspeichert.
// Die App laedt data.js alle 2 Sekunden neu - neue Fotos stehen sofort zur Auswahl, auch ohne Internet.
// Im Browser/Demo: erzeugte Beispielfotos (Alpine-Coaster-Szenen) ohne echte Gaeste.
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
function hash(str: string) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619);
  return h >>> 0;
}
const pick = <T,>(list: T[], r: () => number) => list[Math.floor(r() * list.length)];

const JACKETS = ['#ff5a36', '#ffd23f', '#3ddc97', '#4cc9f0', '#f72585', '#f8f9fa', '#7209b7', '#ff8800', '#00b4d8'];
const SKIN = ['#f1c27d', '#e0ac69', '#c68642', '#8d5524', '#ffdbac'];
const HELMET = ['#222831', '#f5f5f5', '#ffbe0b', '#3a86ff', '#e63946'];
const SLED = ['#e63946', '#f77f00', '#2a9d8f', '#3a86ff', '#8338ec', '#ff006e'];

const sceneCache = new Map<string, string>();

/** Beispielfoto: Alpine Coaster vor Bergen, Tageszeit passend zur Uhrzeit, 1-2 Fahrgaeste. */
export function scene(key: string, ts: number): string {
  const hit = sceneCache.get(key);
  if (hit) return hit;
  const r = rng(hash(key));
  const h = new Date(ts * 1000).getHours();
  const [s1, s2] = h < 11 ? ['#6db8ff', '#e6f4ff'] : h < 15 ? ['#2f86ff', '#bfe0ff'] : h < 18 ? ['#4a78d6', '#ffd3a1'] : ['#2c3766', '#ff9a6a'];
  const ridge = (base: number, amp: number, n: number) => {
    let d = `M0 400 L0 ${base}`;
    for (let i = 0; i <= n; i++) d += ` L${((i / n) * 600).toFixed(0)} ${(base - r() * amp).toFixed(0)}`;
    return d + ' L600 400 Z';
  };
  let trees = '';
  for (let i = 0; i < 36; i++) {
    const x = i * 17 + r() * 10 - 5, s = 18 + r() * 18, y = 302 - r() * 12;
    trees += `<path d="M${x.toFixed(1)} ${(y - s).toFixed(1)} l${(s / 2.6).toFixed(1)} ${s.toFixed(1)} h-${(s / 1.3).toFixed(1)} z" fill="${r() > 0.5 ? '#1d4a37' : '#275e45'}"/>`;
  }
  const P = [[-20, 380], [140, 300], [320, 340], [620, 255]];
  const t = 0.34 + r() * 0.32;
  const bz = (i: number) => (1 - t) ** 3 * P[0][i] + 3 * (1 - t) ** 2 * t * P[1][i] + 3 * (1 - t) * t * t * P[2][i] + t ** 3 * P[3][i];
  const bd = (i: number) => 3 * (1 - t) ** 2 * (P[1][i] - P[0][i]) + 6 * (1 - t) * t * (P[2][i] - P[1][i]) + 3 * t * t * (P[3][i] - P[2][i]);
  const ang = (Math.atan2(bd(1), bd(0)) * 180) / Math.PI;
  const riders = r() > 0.45 ? 2 : 1;
  let people = '';
  for (let i = 0; i < riders; i++) {
    const x = (riders === 2 ? -12 : 0) + i * 24;
    const jacket = pick(JACKETS, r);
    if (r() > 0.45) people += `<path d="M${x - 8} -32 l-10 -18 M${x + 8} -32 l10 -18" stroke="${jacket}" stroke-width="5.5" stroke-linecap="round"/>`;
    people += `<rect x="${x - 9}" y="-40" width="18" height="25" rx="6" fill="${jacket}"/><circle cx="${x}" cy="-48" r="8.5" fill="${pick(SKIN, r)}"/><path d="M${x - 9.5} -49 a9.5 9.5 0 0 1 19 0 z" fill="${pick(HELMET, r)}"/>`;
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400" width="1200" height="800">` +
    `<defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${s1}"/><stop offset="1" stop-color="${s2}"/></linearGradient>` +
    `<linearGradient id="m" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#74c37a"/><stop offset="1" stop-color="#2f6f45"/></linearGradient></defs>` +
    `<rect width="600" height="400" fill="url(#s)"/><circle cx="${(80 + r() * 440).toFixed(0)}" cy="${(52 + r() * 40).toFixed(0)}" r="24" fill="#fff8dc" opacity=".85"/>` +
    `<path d="${ridge(205, 115, 7)}" fill="#a3b9d3"/><path d="${ridge(262, 82, 6)}" fill="#5f7d9c"/>${trees}` +
    `<rect y="300" width="600" height="100" fill="url(#m)"/>` +
    `<path d="M-20 380 C140 300 320 340 620 255" stroke="#dfe5ec" stroke-width="14" fill="none"/>` +
    `<path d="M-20 380 C140 300 320 340 620 255" stroke="#8d99a6" stroke-width="4" fill="none"/>` +
    `<g transform="translate(${bz(0).toFixed(1)} ${(bz(1) - 6).toFixed(1)}) rotate(${ang.toFixed(1)})">` +
    `<path d="M-62 -22 h-44 M-70 -11 h-60 M-60 -32 h-30" stroke="#ffffff" stroke-opacity=".75" stroke-width="3" stroke-linecap="round"/>` +
    `${people}<rect x="-38" y="-18" width="76" height="16" rx="7" fill="${pick(SLED, r)}"/><rect x="-30" y="-4" width="60" height="5" rx="2" fill="#2b2f36"/></g></svg>`;
  const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  sceneCache.set(key, url);
  return url;
}

export const photoSrc = (p: Photo) => p.thumb || p.src || scene(p.key, p.ts);
export const photoFull = (p: Photo) => p.src || scene(p.key, p.ts);

function sample(n: number, ts: number): Photo {
  const number = String(n % 10000).padStart(4, '0');
  return { key: `demo-${n}`, src: '', number, ts, code: `4456${number}${String(ts).slice(-8)}` };
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
