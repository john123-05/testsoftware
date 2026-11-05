// Gutscheine und Tagespass - offline pruefbar.
//
// Ein Code hat 8 Zeichen aus A-Z ohne I/O und 2-9 (keine Verwechslung mit 1/0):
//   Tagespass   D + Tag(2) + Zufall(2) + Pruefung(3)    gilt nur an dem Tag
//   Fotoguthaben P + Anzahl(A=1 ... J=9) + Zufall(3) + Pruefung(3)  gilt einmal
// Pruefung = die ersten 3 Zeichen von HMAC-SHA256(Schluessel, Code ohne Pruefung).
// Der Schluessel kommt aus dem CRM (vouchers.secret); dort werden die Codes auch erzeugt
// (gleicher Algorithmus). So funktioniert der Automat auch ohne Internet.
import type { Voucher } from './hardware';

export const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const EPOCH = Date.UTC(2024, 0, 1);
const USED_KEY = 'lp-kiosk-vouchers-used';

/** Tagesnummer (lokaler Kalendertag) seit 1.1.2024, 2 Zeichen = 1024 Tage Umlauf. */
export function dayIndex(d = new Date()): number {
  const local = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.floor((local - EPOCH) / 86_400_000);
}
export function dayChars(index: number): string {
  const n = ((index % 1024) + 1024) % 1024;
  return ALPHABET[Math.floor(n / 32)] + ALPHABET[n % 32];
}

async function check(secret: string, body: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = new Uint8Array(await crypto.subtle.sign('HMAC', key, enc.encode(body)));
  return ALPHABET[sig[0] % 32] + ALPHABET[sig[1] % 32] + ALPHABET[sig[2] % 32];
}

function used(): string[] {
  try { return JSON.parse(localStorage.getItem(USED_KEY) || '[]') as string[]; } catch { return []; }
}
/** Fotoguthaben gilt einmal: nach dem Kauf hier vermerken. */
export function markUsed(code: string) {
  try { localStorage.setItem(USED_KEY, JSON.stringify([...used(), code].slice(-2000))); } catch { /* egal */ }
}

export async function checkVoucher(code: string, secret: string, now = new Date()): Promise<Voucher | null> {
  const c = code.trim().toUpperCase();
  if (!secret || c.length !== 8 || [...c].some((ch) => !ALPHABET.includes(ch))) return null;
  if (!globalThis.crypto?.subtle) return null;
  if ((await check(secret, c.slice(0, 5))) !== c.slice(5)) return null;
  if (c[0] === 'D') {
    return c.slice(1, 3) === dayChars(dayIndex(now)) ? { code: c, kind: 'day' } : null;
  }
  const photos = ALPHABET.indexOf(c[1]) + 1;
  if (c[0] === 'P' && photos >= 1 && photos <= 9) {
    return used().includes(c) ? null : { code: c, kind: 'photos', photos };
  }
  return null;
}

/** Codes erzeugen (CRM, Tests). */
export async function makeVoucher(secret: string, kind: 'day' | 'photos', opts: { day?: Date; photos?: number } = {}): Promise<string> {
  const rnd = (n: number) => Array.from(crypto.getRandomValues(new Uint8Array(n)), (b) => ALPHABET[b % 32]).join('');
  const body = kind === 'day'
    ? 'D' + dayChars(dayIndex(opts.day ?? new Date())) + rnd(2)
    : 'P' + ALPHABET[Math.max(1, Math.min(9, Math.round(opts.photos ?? 1))) - 1] + rnd(3);
  return body + (await check(secret, body));
}
