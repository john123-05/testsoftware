// Ablauf des Verkaufsprogramms: welcher Bildschirm, Suche, Warenkorb, Zahlung, Bestellung.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { FORMATS, LANGS, printHomeLink, type Format, type KioskConfig, type Lang, type PayMethod, type Tier } from './config';
import { LOCALES, translate } from './i18n';
import { priceCart, type Item, type Pricing } from './pricing';
import type { Hardware, HwStatus, SaleRecord, Voucher } from './hardware';
import { markUsed } from './vouchers';
import { inDay, type Photo } from './data';

export type Screen = 'attract' | 'gallery' | 'scan' | 'print_home' | 'detail' | 'number' | 'face' | 'products' | 'cart' | 'method' | 'card' | 'cash' | 'phone' | 'voucher' | 'success';
export type Overlay = 'help' | 'handoff' | 'idle' | 'admin' | 'lang' | null;
export type Search = { mode: 'recent' | 'time' | 'face' | 'all'; time?: number; faceKeys?: string[] };
export type Order = { items: Item[]; total: number; method: PayMethod | 'free' | 'online_pickup'; photos?: Photo[]; change: number; ts: number };
export type MethodOption = { id: PayMethod; screen: Screen; disabled: boolean; note?: string };

export const BUY_SCREENS: Screen[] = ['print_home', 'products', 'cart', 'method', 'card', 'cash', 'phone'];
export const PAY_SCREENS: Screen[] = ['card', 'cash', 'phone'];

export type Kiosk = {
  cfg: KioskConfig; hw: Hardware; hwStatus: HwStatus; tier: Tier; portrait: boolean; stageScale: number;
  photos: Photo[]; today: Photo[]; byKey: Map<string, Photo>; formats: Format[];
  lang: Lang; setLang: (l: Lang) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
  money: (cents: number) => string; time: (ts: number) => string; hour: (h: number) => string;
  screen: Screen; go: (s: Screen, opts?: { replace?: boolean }) => void; back: () => void; backTo: (s: Screen) => void;
  start: (lang?: Lang) => void; restart: () => void; reset: () => void;
  overlay: Overlay; setOverlay: (o: Overlay) => void;
  search: Search; find: (s: Search, replace?: boolean) => void;
  detail: string | null; detailList: string[]; openDetail: (key: string, list?: string[], replace?: boolean) => void;
  cart: Item[]; buying: string | null; startBuy: (key: string) => void; choose: (f: Format) => void; remove: (i: number) => void;
  pricing: Pricing; methods: MethodOption[]; pay: () => void;
  voucher: Voucher | null; setVoucher: (v: Voucher | null) => void;
  credit: number; setCredit: (c: number) => void;
  order: Order | null; finish: (m: PayMethod | 'free', change?: number) => void;
  finishPickup: (photos: Photo[]) => void;
  busy: boolean; setBusy: (b: boolean) => void;
  searchingSince: number;
  link: (template: string, codes: string[], time?: number) => string;
};

const Ctx = createContext<Kiosk | null>(null);
export function useKiosk(): Kiosk {
  const k = useContext(Ctx);
  if (!k) throw new Error('KioskProvider fehlt');
  return k;
}

/** Betrag je Foto: die Summe nach Listenpreis verteilt (Pakete, Tagespass) - fuer Statistic.txt. */
export function saleRecord(o: Order, lines: { item: Item; photo?: Photo }[], unit: Record<Format, number>, voucher: Voucher | null): SaleRecord {
  const list = lines.map((l) => unit[l.item.format] ?? 0);
  const sum = list.reduce((a, b) => a + b, 0);
  let rest = o.total;
  const prices = list.map((u, i) => {
    if (i === list.length - 1) return rest;
    const share = sum > 0 ? Math.round((o.total * u) / sum) : Math.floor(o.total / list.length);
    rest -= share;
    return share;
  });
  const d = new Date(o.ts);
  const off = -d.getTimezoneOffset();
  const pad = (n: number) => String(Math.trunc(Math.abs(n))).padStart(2, '0');
  const at = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}${off >= 0 ? '+' : '-'}${pad(off / 60)}:${pad(off % 60)}`;
  return {
    id: `${o.ts.toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    at, method: o.method, amount_cents: o.total, change_cents: o.change, voucher: voucher?.code ?? null,
    items: lines.map((l, i) => ({
      key: l.item.key, file: l.photo?.file, code: l.photo?.code, number: l.photo?.number ?? '',
      format: l.item.format, price_cents: prices[i],
    })),
  };
}

const SALES_KEY = 'lp-kiosk-sales';
export type Sale = { ts: number; total: number; method: string; items: number };
export function salesToday(): Sale[] {
  try {
    const all = JSON.parse(localStorage.getItem(SALES_KEY) || '[]') as Sale[];
    const start = new Date(); start.setHours(0, 0, 0, 0);
    return all.filter((s) => s.ts >= start.getTime());
  } catch { return []; }
}
function logSale(o: Order) {
  try {
    const keep = salesToday();
    keep.push({ ts: o.ts, total: o.total, method: o.method, items: o.items.length });
    localStorage.setItem(SALES_KEY, JSON.stringify(keep.slice(-500)));
  } catch { /* nur Statistik */ }
}

export function KioskProvider({ cfg, hw, tier, portrait, stageScale, photos, children }: {
  cfg: KioskConfig; hw: Hardware; tier: Tier; portrait: boolean; stageScale: number; photos: Photo[]; children: ReactNode;
}) {
  const params = useMemo(() => new URLSearchParams(location.search), []);
  // Nur Demo: mit ?screen=... direkt auf einen Bildschirm springen (fuer Vorschau und Tests).
  const requested = hw.mode === 'sim' ? params.get('screen') : null;
  const dev = requested === 'home' || requested === 'time' ? 'gallery' :
    ['attract', 'gallery', 'scan', 'print_home', 'detail', 'number', 'face', ...BUY_SCREENS, 'voucher', 'success'].find((s) => s === requested) as Screen | undefined;
  const landing: Screen = cfg.attract.enabled ? 'attract' : 'gallery';
  const formats = useMemo(() => FORMATS.filter((f) => cfg.products[f].enabled), [cfg.products]);
  const devCart: Item[] = dev && ['cart', 'method', ...PAY_SCREENS, 'success'].includes(dev)
    ? photos.slice(1, 3).map((p, i) => ({ key: p.key, format: formats[(i + formats.length - 1) % formats.length] ?? 'digital' }))
    : [];

  const [lang, setLang] = useState<Lang>(() => LANGS.find((l) => l.id === params.get('lang'))?.id ?? cfg.language);
  const [screen, setScreen] = useState<Screen>(dev || landing);
  const [stack, setStack] = useState<Screen[]>(dev && dev !== 'attract' && dev !== 'gallery' ? ['gallery'] : []);
  const [overlay, setOverlay] = useState<Overlay>(null);
  const [search, setSearch] = useState<Search>({ mode: dev === 'gallery' ? 'all' : 'recent' });
  const [detail, setDetail] = useState<string | null>(dev === 'detail' ? photos[3]?.key ?? null : null);
  const [detailList, setDetailList] = useState<string[]>([]);
  const [cart, setCart] = useState<Item[]>(devCart);
  const [buying, setBuying] = useState<string | null>((dev === 'products' || dev === 'print_home') ? photos[3]?.key ?? null : null);
  const [voucher, setVoucher] = useState<Voucher | null>(null);
  const [credit, setCreditState] = useState<{ cents: number; until: number }>({ cents: 0, until: 0 });
  const [order, setOrder] = useState<Order | null>(dev === 'success' ? { items: devCart, total: 1400, method: 'card', change: 0, ts: Date.now() } : null);
  const [busy, setBusy] = useState(false);
  const [searchingSince, setSearchingSince] = useState(0);
  const [hwStatus, setHwStatus] = useState<HwStatus>(hw.status);
  const screenRef = useRef(screen);
  screenRef.current = screen;
  const stackRef = useRef(stack);
  stackRef.current = stack;

  useEffect(() => hw.on('status', setHwStatus), [hw]);
  useEffect(() => { setHwStatus(hw.status); }, [hw]);

  useEffect(() => { if (!dev && (screenRef.current === 'attract' || !stackRef.current.length)) setScreen(landing); }, [landing, dev]);
  useEffect(() => { if (!params.has('lang')) setLang(cfg.language); }, [cfg.language, params]);

  // Guthaben (zu viel eingeworfen, ohne Wechselgeld) gilt 10 Minuten.
  useEffect(() => {
    if (!credit.cents) return;
    const id = window.setTimeout(() => setCreditState({ cents: 0, until: 0 }), Math.max(0, credit.until - Date.now()));
    return () => window.clearTimeout(id);
  }, [credit]);
  const setCredit = useCallback((cents: number) => setCreditState({ cents, until: Date.now() + 10 * 60_000 }), []);

  // Wie lange jemand schon sucht - fuer die Hilfe-Hinweise.
  useEffect(() => {
    if (['gallery', 'detail', 'number', 'face', 'scan'].includes(screen)) setSearchingSince((s) => s || Date.now());
    else if (screen === 'attract' || BUY_SCREENS.includes(screen) || screen === 'success') setSearchingSince(0);
  }, [screen]);

  const t = useCallback((key: string, p?: Record<string, string | number>) => translate(lang, key, p), [lang]);
  const locale = lang === 'en' && cfg.currency === 'USD' ? 'en-US' : LOCALES[lang];
  const moneyFmt = useMemo(() => new Intl.NumberFormat(locale, { style: 'currency', currency: cfg.currency }), [locale, cfg.currency]);
  const timeFmt = useMemo(() => new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: '2-digit', hour12: cfg.time_format === '12h' }), [locale, cfg.time_format]);
  const hourFmt = useMemo(() => new Intl.DateTimeFormat(locale, { hour: 'numeric', hour12: cfg.time_format === '12h' }), [locale, cfg.time_format]);
  const money = useCallback((c: number) => moneyFmt.format(c / 100), [moneyFmt]);
  const time = useCallback((ts: number) => timeFmt.format(new Date(ts * 1000)), [timeFmt]);
  const hour = useCallback((h: number) => {
    if (cfg.time_format === '24h') return `${String(h).padStart(2, '0')}:00`;
    const d = new Date(); d.setHours(h, 0, 0, 0);
    return hourFmt.format(d);
  }, [cfg.time_format, hourFmt]);

  const byKey = useMemo(() => new Map(photos.map((p) => [p.key, p])), [photos]);
  const today = useMemo(() => photos.filter((p) => inDay(p)), [photos]);
  const pricing = useMemo(() => priceCart(cart, cfg, voucher), [cart, cfg, voucher]);

  const go = useCallback((s: Screen, opts?: { replace?: boolean }) => {
    if (!opts?.replace) setStack((st) => [...st, screenRef.current]);
    setScreen(s);
    setOverlay(null);
  }, []);
  const back = useCallback(() => {
    const st = stackRef.current;
    setStack(st.slice(0, -1));
    setScreen(st[st.length - 1] ?? 'gallery');
    setOverlay(null);
  }, []);
  const backTo = useCallback((s: Screen) => {
    const st = stackRef.current;
    const i = st.lastIndexOf(s);
    if (i >= 0) { setStack(st.slice(0, i)); setScreen(s); } else go(s);
  }, [go]);

  const clearSession = () => {
    setStack([]); setOverlay(null); setSearch({ mode: 'recent' }); setDetail(null); setDetailList([]);
    setCart([]); setBuying(null); setVoucher(null); setOrder(null); setBusy(false); setSearchingSince(0);
  };
  const reset = () => { clearSession(); setLang(cfg.language); setScreen(landing); if (landing === 'gallery') setSearchingSince(Date.now()); };
  const restart = () => { clearSession(); setScreen('gallery'); setSearchingSince(Date.now()); };
  const start = (l?: Lang) => { if (l) setLang(l); setStack([]); setScreen('gallery'); };

  const find = (s: Search, replace = false) => {
    setSearch(s);
    if (screenRef.current !== 'gallery') backTo('gallery');
    if (replace && screenRef.current !== 'gallery' && !stackRef.current.includes('gallery')) setStack([]);
  };
  const openDetail = (key: string, list?: string[], replace = false) => {
    setDetail(key);
    if (list) setDetailList(list);
    if (screenRef.current === 'detail') setScreen('detail'); else go('detail', { replace });
  };

  const defaultFormat: Format = formats.includes('combo') ? 'combo' : formats.includes('digital') ? 'digital' : formats[0] ?? 'digital';
  const startBuy = (key: string) => {
    if (cart.some((i) => i.key === key)) { go('cart'); return; }
    const canShip = printHomeLink(cfg.links.print_home, byKey.get(key)?.code);
    if (!formats.length && !canShip) return;
    if (!canShip && (formats.length === 1 || cfg.express)) {
      setCart((c) => [...c, { key, format: cfg.express ? defaultFormat : formats[0] }]);
      go('cart');
      return;
    }
    setBuying(key);
    go('products');
  };
  const choose = (f: Format) => {
    if (!buying) return;
    setCart((c) => [...c, { key: buying, format: f }]);
    setBuying(null);
    go('cart', { replace: true });
  };
  const remove = (i: number) => setCart((c) => c.filter((_, j) => j !== i));

  const allDigital = cart.every((i) => i.format === 'digital');
  const methods: MethodOption[] = [];
  if (cfg.payments.card) methods.push({ id: 'card', screen: 'card', disabled: !hwStatus.card, note: hwStatus.card ? undefined : t('method.unavailable') });
  if (cfg.payments.cash) methods.push({ id: 'cash', screen: 'cash', disabled: !hwStatus.cash, note: !hwStatus.cash ? t('method.unavailable') : cfg.cash.gives_change && hwStatus.change ? undefined : t('method.cash_nochange') });
  if (cfg.payments.phone) methods.push({ id: 'phone', screen: 'phone', disabled: !allDigital, note: allDigital ? undefined : t('method.digital_only') });
  if (cfg.payments.voucher) methods.push({ id: 'voucher', screen: 'voucher', disabled: false });

  const finish = (m: PayMethod | 'free', change = 0) => {
    const o: Order = { items: cart, total: pricing.total, method: m, change, ts: Date.now() };
    setOrder(o);
    logSale(o);
    // Bezahlt wird auf dem Handy im Shop - der Verkauf zaehlt dort, nicht hier.
    if (m !== 'phone') hw.sale(saleRecord(o, cart.map((i) => ({ item: i, photo: byKey.get(i.key) })), pricing.unit, voucher));
    if (voucher?.kind === 'photos') markUsed(voucher.code);
    setStack([]);
    setOverlay(null);
    setBusy(false);
    setScreen('success');
  };
  const finishPickup = (photos: Photo[]) => {
    clearSession();
    setOrder({ items: photos.map((p) => ({ key: p.key, format: 'print' })), photos, total: 0, method: 'online_pickup', change: 0, ts: Date.now() });
    setBusy(true);
    setScreen('success');
  };
  const pay = () => {
    if (!cart.length) return;
    if (pricing.total === 0) { finish('free'); return; }
    const usable = methods.filter((m) => !m.disabled);
    if (usable.length === 1) go(usable[0].screen); else go('method');
  };

  const link = (template: string, codes: string[], ts?: number) => {
    const d = new Date((ts ?? Date.now() / 1000) * 1000);
    const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    return template.split('{codes}').join(codes.join(',')).split('{code}').join(codes[0] ?? '').split('{time}').join(hm);
  };

  const value: Kiosk = {
    cfg, hw, hwStatus, tier, portrait, stageScale, photos, today, byKey, formats,
    lang, setLang, t, money, time, hour,
    screen, go, back, backTo, start, restart, reset, overlay, setOverlay,
    search, find, detail, detailList, openDetail,
    cart, buying, startBuy, choose, remove, pricing, methods, pay,
    voucher, setVoucher, credit: credit.cents, setCredit, order, finish, finishPickup, busy, setBusy, searchingSince, link,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
