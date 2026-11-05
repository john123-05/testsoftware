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
  attract: { enabled: boolean; after_seconds: number; slide_seconds: number; messages: Record<Lang, string[]>; show_photos: boolean; headline: string; subline: string; phone_qr: boolean; show_count: boolean };
  find: { just_rode_minutes: number; time: boolean; number: boolean; face: boolean; phone: boolean; scan: boolean };
  products: Record<Format, { enabled: boolean; price: number }>;
  packages: Package[];
  payments: Record<PayMethod, boolean>;
  cash: { gives_change: boolean; denominations: number[] };
  /** Wo am Automaten das Geraet sitzt - dorthin zeigt der Pfeil auf dem Bildschirm. */
  devices: { card: Pos; cash: Pos; printer: Pos };
  /** {code} = erster Code, {codes} = alle Codes (Komma), {time} = HH:MM */
  links: { phone_search: string; phone_pay: string; download: string; print_home: string };
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
  theme: { preset: 'clean', brand: null, accent: null, logo: null, background: null },
  attract: {
    enabled: true, after_seconds: 45, slide_seconds: 5, show_photos: true,
    headline: '', subline: '', phone_qr: false, show_count: false,
    messages: {
      de: ['Dein Foto von der Fahrt', 'Hier kaufen und mitnehmen', 'Jetzt drucken lassen'],
      en: ['Your ride photo', 'Buy it here', 'Printed in seconds'],
      fr: ['Ta photo de l’aventure', 'Achète-la ici', 'Imprimée en quelques secondes'],
      es: ['Tu foto de la aventura', 'Cómprala aquí', 'Imprime en segundos'],
      it: ['La foto della tua corsa', 'Comprala qui', 'Stampata in pochi secondi'],
      nl: ['Jouw ritfoto', 'Koop je foto hier', 'Binnen enkele seconden geprint'],
    },
  },
  find: { just_rode_minutes: 10, time: true, number: true, face: true, phone: true, scan: false },
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
    print_home: '',
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
  clean: { label: 'Clean', scheme: 'light', bg: '#f6f7f9', bg2: '#ffffff', surface: '#ffffff', surface2: '#edf0ef', line: '#ccd3d0', text: '#111111', muted: '#4e5955', brand: '#14624d', brandInk: '#ffffff', accent: '#14624d', accentInk: '#ffffff' },
  dark: { label: 'Dark', scheme: 'dark', bg: '#171a19', bg2: '#212524', surface: '#212524', surface2: '#303734', line: '#57655f', text: '#ffffff', muted: '#d4ded9', brand: '#8ee0ba', brandInk: '#111111', accent: '#8ee0ba', accentInk: '#111111' },
};

export function themePreset(id: string): string {
  if (['alpine', 'night', 'sunset'].includes(id)) return 'dark';
  return Object.prototype.hasOwnProperty.call(THEMES, id) ? id : 'clean';
}

export function printHomeLink(template: string, code?: string): string {
  if (!code || !template.includes('{code}')) return '';
  try {
    const url = new URL(template.split('{code}').join(encodeURIComponent(code)));
    return url.protocol === 'https:' ? url.href : '';
  } catch { return ''; }
}

// Nur bekannte Schluessel uebernehmen, Typen pruefen - eine kaputte Einstellung darf den Automaten nie stoppen.
function merge<T>(base: T, raw: unknown): T {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return base;
  const out = { ...(base as Record<string, unknown>) };
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (!Object.prototype.hasOwnProperty.call(out, k)) continue;
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
  const attract = { ...c.attract, messages: { ...c.attract.messages } };
  for (const { id } of LANGS) {
    const messages = attract.messages[id].filter((m) => typeof m === 'string' && m.trim()).slice(0, 30).map((m) => m.trim().slice(0, 500));
    attract.messages[id] = messages.length ? messages : DEFAULT_CONFIG.attract.messages[id];
  }
  const hasAttractDelay = layers.some((layer) => typeof (layer as { attract?: { after_seconds?: unknown } } | null)?.attract?.after_seconds === 'number');
  return {
    ...c,
    attract: { ...attract, after_seconds: Math.max(15, Math.min(300, hasAttractDelay ? attract.after_seconds : c.idle_seconds)), slide_seconds: Math.max(2, Math.min(60, attract.slide_seconds)) },
    languages: langs.length ? langs : DEFAULT_CONFIG.languages,
    language: LANGS.some((x) => x.id === c.language) ? c.language : 'en',
    theme: { ...c.theme, preset: themePreset(c.theme.preset) },
    idle_seconds: Math.max(15, Math.min(300, c.idle_seconds)),
    help_seconds: Math.max(8, Math.min(120, c.help_seconds)),
    find: { ...c.find, just_rode_minutes: Math.max(2, Math.min(60, c.find.just_rode_minutes)) },
    packages: c.packages.filter((p) => p && FORMATS.includes(p.format) && p.photos > 1 && p.price > 0),
    cash: { ...c.cash, denominations: c.cash.denominations.filter((d) => Number.isInteger(d) && d > 0).sort((a, b) => a - b) },
    admin_pin: /^\d{4,8}$/.test(c.admin_pin) ? c.admin_pin : DEFAULT_CONFIG.admin_pin,
  };
}
