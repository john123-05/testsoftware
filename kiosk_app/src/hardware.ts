// Anbindung an die Geraete des Automaten.
//
// Im Automaten laeuft die App im Programm "Liftpictures Display" (WebView2). Das Programm spricht die
// Geraete an - Kartenterminal (ZVT ueber easyzvt.exe, wie das alte Verkaufsprogramm), Muenzpruefer
// (NRI ueber PaymentManager), Drucker, Gesichtssuche (FaceAiSharp) - und meldet sich ueber
// chrome.webview-Nachrichten: {type:'hw', id, method, args} -> {type:'hw-result', id, result},
// Ereignisse als {type:'hw-event', event, value}.
//
// Ohne dieses Programm (Browser, Demo) laeuft alles im Simulator: Muenzen, Karte, Drucker, Gesicht
// lassen sich im Simulator-Feld ausloesen; Zahlungen gehen sonst nach ein paar Sekunden von selbst durch.
import QRCode from 'qrcode';
import type { Photo } from './data';
import { checkVoucher } from './vouchers';

export type CardResult = 'approved' | 'declined' | 'timeout' | 'cancelled' | 'error';
export type PrinterState = 'ready' | 'printing' | 'paper_out' | 'offline';
export type HwStatus = { card: boolean; cash: boolean; change: boolean; printer: PrinterState; face: boolean; camera: boolean };
export type { Voucher } from './vouchers';
import type { Voucher } from './vouchers';
export type HwEvents = { coin: number; status: HwStatus; print: { done: number; total: number }; card: 'waiting' | 'processing' };
/** Welche Geraete die Einstellungen brauchen - nur die startet das Programm. */
export type Devices = { card: boolean; cash: boolean; printer: boolean; face: boolean };
export type PrintOptions = { qr: boolean; date: boolean; logo: boolean };
/** Ein Verkauf, wie ihn Liftpictures Display in Statistic.txt und sales/JJJJ-MM-TT.jsonl schreibt. */
export type SaleRecord = {
  id: string; at: string; method: string; amount_cents: number; change_cents: number; voucher: string | null;
  items: { key: string; file?: string; code?: string; number: string; format: string; price_cents: number }[];
};

export interface Hardware {
  mode: 'sim' | 'host';
  status: HwStatus;
  on<K extends keyof HwEvents>(event: K, cb: (v: HwEvents[K]) => void): () => void;
  cashEnable(dueCents: number): void;
  cashDisable(): void;
  cashPayout(cents: number): Promise<number>;
  cardPay(cents: number): Promise<CardResult>;
  cardCancel(): void;
  print(photos: Photo[], opts?: PrintOptions): Promise<boolean>;
  faceSearch(image: string | null, candidates: Photo[]): Promise<string[]>;
  /** Ob das Programm eine Handy-Zahlung bestaetigen kann. Sonst tippt der Gast auf "Fertig". */
  phoneConfirms: boolean;
  phonePaid(url: string): Promise<boolean>;
  phoneCancel(): void;
  voucherCheck(code: string, secret: string): Promise<Voucher | null>;
  configure(devices: Devices): void;
  sale(rec: SaleRecord): void;
  exit(): void;
}

const sleep = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms));

class Emitter {
  private listeners = new Map<string, Set<(v: never) => void>>();
  on<K extends keyof HwEvents>(event: K, cb: (v: HwEvents[K]) => void): () => void {
    const set = this.listeners.get(event) ?? new Set();
    set.add(cb as (v: never) => void);
    this.listeners.set(event, set);
    return () => { set.delete(cb as (v: never) => void); };
  }
  protected emit<K extends keyof HwEvents>(event: K, value: HwEvents[K]) {
    this.listeners.get(event)?.forEach((cb) => (cb as (v: HwEvents[K]) => void)(value));
  }
}

export class SimHardware extends Emitter implements Hardware {
  mode = 'sim' as const;
  status: HwStatus = { card: true, cash: true, change: true, printer: 'ready', face: true, camera: true };
  /** Demo: Karte und Handy-Zahlung gehen nach ein paar Sekunden von selbst durch. */
  auto = true;
  cashOn = false;
  private cardResolve: ((r: CardResult) => void) | null = null;
  private cardTimer = 0;
  private phoneResolve: ((ok: boolean) => void) | null = null;
  private phoneTimer = 0;
  faceFinds = true;

  setStatus(patch: Partial<HwStatus>) { this.status = { ...this.status, ...patch }; this.emit('status', this.status); }
  insert(cents: number) { if (this.cashOn) this.emit('coin', cents); }
  cashEnable() { this.cashOn = true; }
  cashDisable() { this.cashOn = false; }
  async cashPayout(cents: number) { await sleep(900); return cents; }

  cardPay(): Promise<CardResult> {
    window.clearTimeout(this.cardTimer);
    return new Promise((resolve) => {
      this.cardResolve = resolve;
      this.emit('card', 'waiting');
      if (this.auto) this.cardTimer = window.setTimeout(() => this.simCard('approved'), 4200);
    });
  }
  /** Simulator: Karte aufgelegt -> Ergebnis nach kurzer Pruefung. */
  simCard(result: CardResult) {
    if (!this.cardResolve) return;
    window.clearTimeout(this.cardTimer);
    this.emit('card', 'processing');
    this.cardTimer = window.setTimeout(() => this.finishCard(result), 1600);
  }
  private finishCard(result: CardResult) {
    window.clearTimeout(this.cardTimer);
    const done = this.cardResolve;
    this.cardResolve = null;
    done?.(result);
  }
  cardCancel() { this.finishCard('cancelled'); }

  async print(photos: Photo[]) {
    if (this.status.printer !== 'ready') { await sleep(1800); return false; }
    this.setStatus({ printer: 'printing' });
    for (let i = 0; i < photos.length; i++) {
      this.emit('print', { done: i, total: photos.length });
      await sleep(2600);
    }
    this.emit('print', { done: photos.length, total: photos.length });
    this.setStatus({ printer: 'ready' });
    return true;
  }

  async faceSearch(_image: string | null, candidates: Photo[]) {
    await sleep(2600);
    if (!this.faceFinds || !candidates.length) return [];
    const pool = candidates.slice(0, 50);
    const n = Math.min(pool.length, 2 + Math.floor(Math.random() * 3));
    const picked = new Set<string>();
    while (picked.size < n) picked.add(pool[Math.floor(Math.random() * pool.length)].key);
    return [...picked];
  }

  phonePaid(): Promise<boolean> {
    window.clearTimeout(this.phoneTimer);
    return new Promise((resolve) => {
      this.phoneResolve = resolve;
      if (this.auto) this.phoneTimer = window.setTimeout(() => this.simPhone(true), 7000);
    });
  }
  simPhone(ok: boolean) {
    window.clearTimeout(this.phoneTimer);
    const done = this.phoneResolve;
    this.phoneResolve = null;
    done?.(ok);
  }
  phoneCancel() { this.simPhone(false); }

  phoneConfirms = true;

  /** Demo-Codes: D + 7 Zeichen = Tagespass (z. B. DAYPASS2), P + Ziffer + 6 Zeichen = so viele Gratis-Fotos (z. B. P2FREE22).
   *  Mit Schluessel aus dem CRM gelten zusaetzlich die echten Codes. */
  async voucherCheck(code: string, secret: string): Promise<Voucher | null> {
    await sleep(700);
    const c = code.toUpperCase();
    const real = await checkVoucher(c, secret);
    if (real) return real;
    if (/^DAYPASS[2-9]$/.test(c)) return { code: c, kind: 'day' };
    const m = /^P([1-5])FREE[A-Z2-9]{2}$/.exec(c);
    return m ? { code: c, kind: 'photos', photos: Number(m[1]) } : null;
  }
  configure() { /* Simulator: alles da */ }
  sale(rec: SaleRecord) { console.info('[kiosk] Verkauf', rec); }
  exit() { /* im Browser nichts zu schliessen */ }
}

type WebView = { postMessage(m: unknown): void; addEventListener(t: 'message', cb: (e: { data: unknown }) => void): void };

export class HostHardware extends Emitter implements Hardware {
  mode = 'host' as const;
  status: HwStatus = { card: false, cash: false, change: false, printer: 'offline', face: false, camera: false };
  /** Bezahlt wird auf dem Handy direkt im Shop - das sieht der Automat nicht. */
  phoneConfirms = false;
  private calls = new Map<number, (v: unknown) => void>();
  private seq = 0;
  private wv: WebView;

  constructor(wv: WebView) {
    super();
    this.wv = wv;
    wv.addEventListener('message', (e) => {
      const d = e.data as { type?: string; id?: number; result?: unknown; event?: keyof HwEvents; value?: unknown };
      if (d?.type === 'hw-result' && typeof d.id === 'number') { this.calls.get(d.id)?.(d.result); this.calls.delete(d.id); }
      else if (d?.type === 'hw-event' && d.event) {
        if (d.event === 'status') this.status = d.value as HwStatus;
        this.emit(d.event, d.value as never);
      }
    });
    void this.call<HwStatus>('status').then((s) => { if (s) { this.status = s; this.emit('status', s); } });
  }
  private call<T>(method: string, ...args: unknown[]): Promise<T> {
    const id = ++this.seq;
    return new Promise((resolve) => { this.calls.set(id, resolve as (v: unknown) => void); this.wv.postMessage({ type: 'hw', id, method, args }); });
  }
  cashEnable(due: number) { void this.call('cashEnable', due); }
  cashDisable() { void this.call('cashDisable'); }
  cashPayout(cents: number) { return this.call<number>('cashPayout', cents); }
  cardPay(cents: number) { return this.call<CardResult>('cardPay', cents); }
  cardCancel() { void this.call('cardCancel'); }
  async print(photos: Photo[], opts: PrintOptions = { qr: true, date: true, logo: true }) {
    // Den QR-Code zeichnet die App (gleiche Bibliothek wie am Bildschirm), das Programm setzt ihn aufs Foto.
    const jobs = await Promise.all(photos.map(async (p) => ({
      file: p.file, number: p.number, ts: p.ts, code: p.code,
      qr: opts.qr && p.url ? await QRCode.toDataURL(p.url, { margin: 1, width: 360, errorCorrectionLevel: 'M' }) : null,
    })));
    return this.call<boolean>('print', jobs, opts);
  }
  async faceSearch(image: string | null, candidates: Photo[]) {
    const byFile = new Map(candidates.filter((p) => p.file).map((p) => [p.file as string, p.key]));
    const files = await this.call<string[]>('faceSearch', image, [...byFile.keys()]);
    return (files ?? []).map((f) => byFile.get(f)).filter((k): k is string => !!k);
  }
  phonePaid() { return new Promise<boolean>(() => { /* siehe phoneConfirms */ }); }
  phoneCancel() { /* nichts offen */ }
  async voucherCheck(code: string, secret: string) { return checkVoucher(code, secret); }
  configure(devices: Devices) { void this.call('configure', devices); }
  sale(rec: SaleRecord) { void this.call('sale', rec); }
  exit() { void this.call('exit'); }
}

export function createHardware(): Hardware {
  const forceSim = new URLSearchParams(location.search).has('sim');
  const wv = (window as unknown as { chrome?: { webview?: WebView } }).chrome?.webview;
  return !forceSim && wv ? new HostHardware(wv) : new SimHardware();
}
