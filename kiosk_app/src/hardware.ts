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
import type { Photo } from './data';

export type CardResult = 'approved' | 'declined' | 'timeout' | 'cancelled' | 'error';
export type PrinterState = 'ready' | 'printing' | 'paper_out' | 'offline';
export type HwStatus = { card: boolean; cash: boolean; change: boolean; printer: PrinterState; face: boolean; camera: boolean };
export type Voucher = { code: string; kind: 'day' } | { code: string; kind: 'photos'; photos: number };
export type HwEvents = { coin: number; status: HwStatus; print: { done: number; total: number }; card: 'waiting' | 'processing' };

export interface Hardware {
  mode: 'sim' | 'host';
  status: HwStatus;
  on<K extends keyof HwEvents>(event: K, cb: (v: HwEvents[K]) => void): () => void;
  cashEnable(dueCents: number): void;
  cashDisable(): void;
  cashPayout(cents: number): Promise<number>;
  cardPay(cents: number): Promise<CardResult>;
  cardCancel(): void;
  print(photos: Photo[]): Promise<boolean>;
  faceSearch(image: string | null, candidates: Photo[]): Promise<string[]>;
  phonePaid(url: string): Promise<boolean>;
  phoneCancel(): void;
  voucherCheck(code: string): Promise<Voucher | null>;
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

  /** Demo-Codes: D + 7 Zeichen = Tagespass (z. B. DAYPASS2), P + Ziffer + 6 Zeichen = so viele Gratis-Fotos (z. B. P2FREE22). */
  async voucherCheck(code: string): Promise<Voucher | null> {
    await sleep(700);
    const c = code.toUpperCase();
    if (/^D[A-Z2-9]{7}$/.test(c)) return { code: c, kind: 'day' };
    const m = /^P([1-5])[A-Z2-9]{6}$/.exec(c);
    return m ? { code: c, kind: 'photos', photos: Number(m[1]) } : null;
  }
  exit() { /* im Browser nichts zu schliessen */ }
}

type WebView = { postMessage(m: unknown): void; addEventListener(t: 'message', cb: (e: { data: unknown }) => void): void };

export class HostHardware extends Emitter implements Hardware {
  mode = 'host' as const;
  status: HwStatus = { card: false, cash: false, change: false, printer: 'offline', face: false, camera: false };
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
  print(photos: Photo[]) { return this.call<boolean>('print', photos.map((p) => ({ key: p.key, src: p.src, number: p.number, ts: p.ts }))); }
  faceSearch(image: string | null, candidates: Photo[]) { return this.call<string[]>('faceSearch', image, candidates.map((p) => p.key)); }
  phonePaid(url: string) { return this.call<boolean>('phonePaid', url); }
  phoneCancel() { void this.call('phoneCancel'); }
  voucherCheck(code: string) { return this.call<Voucher | null>('voucherCheck', code); }
  exit() { void this.call('exit'); }
}

export function createHardware(): Hardware {
  const forceSim = new URLSearchParams(location.search).has('sim');
  const wv = (window as unknown as { chrome?: { webview?: WebView } }).chrome?.webview;
  return !forceSim && wv ? new HostHardware(wv) : new SimHardware();
}
