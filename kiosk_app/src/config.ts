// Einstellungen des Verkaufsprogramms (Liftpictures Kiosk).
// Kommen spaeter aus CRM/Dashboard ueber den Agenten (data.js -> config); hier: Typen, Vorgaben,
// Versionen (Karte / Bargeld / nur digital ...) und Farbwelten.

export type Lang = 'en' | 'de' | 'fr' | 'es' | 'it' | 'nl';
export type PayMethod = 'card' | 'cash' | 'phone' | 'voucher';
export type Format = 'print' | 'digital' | 'combo';
export type Pos = 'below' | 'below-left' | 'below-right' | 'left' | 'right';
export type Tier = 'low' | 'mid' | 'high';

export const LANGS: { id: Lang; code: string; name: string }[] = [
  { id: 'en', code: 'EN', name: 'English' },
  { id: 'de', code: 'DE', name: 'Deutsch' },
  { id: 'fr', code: 'FR', name: 'Français' },
  { id: 'es', code: 'ES', name: 'Español' },
  { id: 'it', code: 'IT', name: 'Italiano' },
  { id: 'nl', code: 'NL', name: 'Nederlands' },
];

export const FORMATS: Format[] = ['print', 'digital', 'combo'];

export type Package = { format: Format; photos: number; price: number };

export type KioskConfig = {
  park_name: string;
  currency: string;
  language: Lang;
  languages: Lang[];
  time_format: '24h' | '12h';
  /** Nur fuer Bildschirme ohne Touch. Touch-Automaten bitte in Windows hochkant stellen. */
  rotation: 0 | 90 | 180 | 270;
  performance: 'auto' | Tier;
  /** Hochbetrieb: Format-Auswahl ueberspringen, Standardformat direkt in den Warenkorb. */
  express: boolean;
  theme: { preset: string; brand: string | null; accent: string | null; logo: string | null; background: string | null };
  attract: { headline: string; subline: string; phone_qr: boolean; show_count: boolean };
  find: { just_rode_minutes: number; time: boolean; number: boolean; face: boolean; phone: boolean };
  products: Record<Format, { enabled: boolean; price: number }>;
  packages: Package[];
  payments: Record<PayMethod, boolean>;
  cash: { gives_change: boolean; denominations: number[] };
  /** Wo am Automaten das Geraet sitzt - dorthin zeigt der Pfeil auf dem Bildschirm. */
  devices: { card: Pos; cash: Pos; printer: Pos };
  /** {code} = erster Code, {codes} = alle Codes (Komma), {time} = HH:MM */
  links: { phone_search: string; phone_pay: string; download: string };
  /** Was auf den Ausdruck kommt (Lage und Groesse stehen in der Settings.xml des Automaten). */
  print: { qr: boolean; date: boolean; logo: boolean };
  /** Gutscheine/Tagespass: Codes werden offline geprueft (Pruefsumme mit diesem Schluessel, aus dem CRM). */
  vouchers: { secret: string };
  idle_seconds: number;
  help_seconds: number;
  admin_pin: string;
};

export const DEFAULT_CONFIG: KioskConfig = {
  park_name: 'Alpine Coaster',
  currency: 'EUR',
  language: 'en',
  languages: ['en', 'de', 'fr', 'es', 'it', 'nl'],
  time_format: '24h',
  rotation: 0,
  performance: 'auto',
  express: false,
  theme: { preset: 'alpine', brand: null, accent: null, logo: null, background: null },
  attract: { headline: '', subline: '', phone_qr: true, show_count: true },
  find: { just_rode_minutes: 10, time: true, number: true, face: true, phone: true },
  products: {
    print: { enabled: true, price: 600 },
    digital: { enabled: true, price: 500 },
    combo: { enabled: true, price: 900 },
  },
  packages: [
    { format: 'digital', photos: 3, price: 1200 },
    { format: 'combo', photos: 3, price: 2200 },
  ],
  payments: { card: true, cash: true, phone: true, voucher: true },
  cash: { gives_change: true, denominations: [10, 20, 50, 100, 200, 500, 1000, 2000] },
  devices: { card: 'below-right', cash: 'below-left', printer: 'below' },
  links: {
    phone_search: 'https://liftpictures-fotos.de/demo?t={time}',
    phone_pay: 'https://liftpictures-fotos.de/demo/shop?codes={codes}',
    download: 'https://liftpictures-fotos.de/demo/claim?code={code}',
  },
  print: { qr: true, date: true, logo: true },
  vouchers: { secret: '' },
  idle_seconds: 45,
  help_seconds: 20,
  admin_pin: '2580',
};

/** Versionen fuer den Verkauf: welche Zahlarten und Produkte ein Automat hat. */
export const EDITIONS: Record<string, { label: string; payments: Record<PayMethod, boolean>; products: Record<Format, boolean> }> = {
  complete: { label: 'Komplett', payments: { card: true, cash: true, phone: true, voucher: true }, products: { print: true, digital: true, combo: true } },
  card_cash: { label: 'Karte + Bargeld', payments: { card: true, cash: true, phone: false, voucher: true }, products: { print: true, digital: true, combo: true } },
  card: { label: 'Nur Karte', payments: { card: true, cash: false, phone: false, voucher: true }, products: { print: true, digital: true, combo: true } },
  cash: { label: 'Nur Bargeld', payments: { card: false, cash: true, phone: false, voucher: true }, products: { print: true, digital: true, combo: true } },
  digital: { label: 'Nur digital', payments: { card: false, cash: false, phone: true, voucher: true }, products: { print: false, digital: true, combo: false } },
};

export function applyEdition(c: KioskConfig, id: string): KioskConfig {
  const e = EDITIONS[id];
  if (!e) return c;
  return {
    ...c,
    payments: { ...e.payments },
    products: {
      print: { ...c.products.print, enabled: e.products.print },
      digital: { ...c.products.digital, enabled: e.products.digital },
      combo: { ...c.products.combo, enabled: e.products.combo },
    },
  };
}

export function editionOf(c: KioskConfig): string | null {
  for (const [id, e] of Object.entries(EDITIONS)) {
    const pay = (Object.keys(e.payments) as PayMethod[]).every((m) => e.payments[m] === c.payments[m]);
    const prod = FORMATS.every((f) => e.products[f] === c.products[f].enabled);
    if (pay && prod) return id;
  }
  return null;
}

export type Theme = {
  label: string; scheme: 'dark' | 'light';
  bg: string; bg2: string; surface: string; surface2: string; line: string;
  text: string; muted: string; brand: string; brandInk: string; accent: string; accentInk: string;
};

export const THEMES: Record<string, Theme> = {
  alpine: { label: 'Alpine', scheme: 'dark', bg: '#06182b', bg2: '#0e3456', surface: 'rgba(255,255,255,.06)', surface2: 'rgba(255,255,255,.11)', line: 'rgba(255,255,255,.12)', text: '#f4f8fc', muted: '#9fb3c8', brand: '#ff6b2c', brandInk: '#ffffff', accent: '#7dd3fc', accentInk: '#06263f' },
  night: { label: 'Night', scheme: 'dark', bg: '#090c14', bg2: '#161d33', surface: 'rgba(255,255,255,.05)', surface2: 'rgba(255,255,255,.1)', line: 'rgba(255,255,255,.1)', text: '#f5f7fb', muted: '#97a3b6', brand: '#3d7bff', brandInk: '#ffffff', accent: '#ffc247', accentInk: '#1a1200' },
  sunset: { label: 'Sunset', scheme: 'dark', bg: '#1a0a1f', bg2: '#4a1530', surface: 'rgba(255,255,255,.06)', surface2: 'rgba(255,255,255,.11)', line: 'rgba(255,255,255,.12)', text: '#fff6f2', muted: '#d1a9b5', brand: '#ff5e57', brandInk: '#ffffff', accent: '#ffd166', accentInk: '#2a1a00' },
  clean: { label: 'Clean', scheme: 'light', bg: '#eef2f7', bg2: '#ffffff', surface: '#ffffff', surface2: '#f1f4f8', line: '#dde3ec', text: '#0f1b2d', muted: '#5b6b80', brand: '#d9480f', brandInk: '#ffffff', accent: '#0e7490', accentInk: '#ffffff' },
};

// Nur bekannte Schluessel uebernehmen, Typen pruefen - eine kaputte Einstellung darf den Automaten nie stoppen.
function merge<T>(base: T, raw: unknown): T {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return base;
  const out = { ...(base as Record<string, unknown>) };
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (!(k in out)) continue;
    const b = out[k];
    if (b && typeof b === 'object' && !Array.isArray(b)) out[k] = merge(b, v);
    else if (Array.isArray(b)) { if (Array.isArray(v)) out[k] = v; }
    else if (b === null) { if (v === null || typeof v === 'string') out[k] = v; }
    else if (typeof v === typeof b) out[k] = v;
  }
  return out as T;
}

/** Ebenen von unten nach oben: Vorgaben, was der Agent weiss (Links, Logo), Einstellungen aus dem CRM. */
export function mergeConfig(...layers: unknown[]): KioskConfig {
  const c = layers.reduce<KioskConfig>((acc, raw) => merge(acc, raw), DEFAULT_CONFIG);
  const langs = c.languages.filter((l) => LANGS.some((x) => x.id === l));
  return {
    ...c,
    languages: langs.length ? langs : DEFAULT_CONFIG.languages,
    language: LANGS.some((x) => x.id === c.language) ? c.language : 'en',
    theme: { ...c.theme, preset: THEMES[c.theme.preset] ? c.theme.preset : 'alpine' },
    idle_seconds: Math.max(15, Math.min(300, c.idle_seconds)),
    help_seconds: Math.max(8, Math.min(120, c.help_seconds)),
    find: { ...c.find, just_rode_minutes: Math.max(2, Math.min(60, c.find.just_rode_minutes)) },
    packages: c.packages.filter((p) => p && FORMATS.includes(p.format) && p.photos > 1 && p.price > 0),
    cash: { ...c.cash, denominations: c.cash.denominations.filter((d) => Number.isInteger(d) && d > 0).sort((a, b) => a - b) },
    admin_pin: /^\d{4,8}$/.test(c.admin_pin) ? c.admin_pin : DEFAULT_CONFIG.admin_pin,
  };
}
