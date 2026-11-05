// Liftpictures Kiosk - neues Verkaufsprogramm fuer Fotoautomaten.
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { DEFAULT_CONFIG, EDITIONS, THEMES, applyEdition, mergeConfig, themePreset, type KioskConfig, type Tier } from './config';
import { createHardware, SimHardware } from './hardware';
import { useKioskData } from './data';
import { useTier } from './perf';
import { KioskProvider, useKiosk, type Screen } from './store';
import { Icon, QR, TopBar } from './ui';
import { Overlays, Blocked } from './overlays';
import { SimPanel, type Frame } from './SimPanel';
import { Attract, FaceScreen, NumberScreen } from './screens/Start';
import { Detail, Gallery } from './screens/Browse';
import { Cart, Method, PrintHome, Products } from './screens/Buy';
import { CardPay, CashPay, PhonePay, Success, VoucherScreen } from './screens/Pay';

import { Scan } from './screens/Scan';

const SCREENS: Record<Screen, () => JSX.Element | null> = {
  attract: Attract, gallery: Gallery, scan: Scan, print_home: PrintHome, detail: Detail, number: NumberScreen, face: FaceScreen,
  products: Products, cart: Cart, method: Method, card: CardPay, cash: CashPay, phone: PhonePay, voucher: VoucherScreen, success: Success,
};

function themeStyle(cfg: KioskConfig): CSSProperties {
  const th = THEMES[cfg.theme.preset] ?? THEMES.clean;
  const brand = cfg.theme.brand ?? cfg.theme.accent ?? th.brand;
  const hex = /^#[0-9a-f]{6}$/i.test(brand) ? brand : th.brand;
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  const ink = channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722 > 0.179 ? '#111111' : '#ffffff';
  const vars: Record<string, string> = {
    '--bg': th.bg, '--bg2': th.bg2, '--surface': th.surface, '--surface2': th.surface2, '--line': th.line,
    '--text': th.text, '--muted': th.muted, '--brand': hex, '--brandInk': ink,
    '--accent': hex, '--accentInk': ink,
  };
  return vars as CSSProperties;
}

/** Nach einer Weile ohne Beruehrung: "Bist du noch da?" - nicht waehrend einer Zahlung. */
function useIdle() {
  const k = useKiosk();
  const last = useRef(Date.now());
  useEffect(() => {
    const touch = () => { last.current = Date.now(); };
    window.addEventListener('pointerdown', touch, true);
    window.addEventListener('keydown', touch, true);
    return () => { window.removeEventListener('pointerdown', touch, true); window.removeEventListener('keydown', touch, true); };
  }, []);
  useEffect(() => { last.current = Date.now(); }, [k.screen, k.overlay]);
  const idleSeconds = k.cfg.attract.enabled ? k.cfg.attract.after_seconds : k.cfg.idle_seconds;
  useEffect(() => {
    const id = window.setInterval(() => {
      if (k.screen === 'attract' || k.screen === 'success' || k.busy || k.overlay === 'idle' || k.overlay === 'admin') return;
      if (Date.now() - last.current > idleSeconds * 1000) k.setOverlay('idle');
    }, 1000);
    return () => window.clearInterval(id);
  }, [k.screen, k.busy, k.overlay, idleSeconds]); // eslint-disable-line react-hooks/exhaustive-deps
}

function SearchHelp() {
  const k = useKiosk();
  const [dismissed, setDismissed] = useState(0);
  const [visibleSince, setVisibleSince] = useState(0);
  useEffect(() => {
    if (!k.searchingSince) return;
    const remaining = k.cfg.help_seconds * 1000 - (Date.now() - k.searchingSince);
    const timer = window.setTimeout(() => setVisibleSince(k.searchingSince), Math.max(0, remaining));
    return () => window.clearTimeout(timer);
  }, [k.searchingSince, k.cfg.help_seconds]);
  if (!k.cfg.find.phone || !k.cfg.links.phone_search || k.overlay ||
      !['gallery', 'detail', 'number'].includes(k.screen) ||
      !k.searchingSince || visibleSince !== k.searchingSince || dismissed === k.searchingSince) return null;
  return <aside className="search-help">
    <QR value={k.link(k.cfg.links.phone_search, [], k.search.time)} size="7rem" />
    <div><strong>{k.t('coach.stuck')}</strong><p>{k.t('coach.stuck_sub')}</p></div>
    <button className="btn btn-ghost" onClick={() => setDismissed(k.searchingSince)} aria-label={k.t('common.close')}><Icon name="x" /></button>
  </aside>;
}

function Shell() {
  const k = useKiosk();
  useIdle();
  const View = SCREENS[k.screen];
  const th = THEMES[k.cfg.theme.preset] ?? THEMES.clean;
  return (
    <div className={`app ${k.portrait ? 'portrait' : 'landscape'}`} style={themeStyle(k.cfg)} data-scheme={th.scheme} data-tier={k.tier}>
      {k.screen !== 'attract' && <TopBar />}
      <main className="main"><View key={k.screen === 'detail' ? `detail-${k.detail}` : k.screen} /></main>
      <SearchHelp />
      <Overlays />
    </div>
  );
}

function useViewport() {
  const [v, setV] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    const f = () => setV({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener('resize', f);
    return () => window.removeEventListener('resize', f);
  }, []);
  return v;
}

export default function App() {
  const hw = useMemo(createHardware, []);
  const sim = hw.mode === 'sim';
  const params = useMemo(() => new URLSearchParams(location.search), []);
  const data = useKioskData(sim);
  const [simCfg, setSimCfg] = useState<KioskConfig>(() => {
    let c = DEFAULT_CONFIG;
    const ed = params.get('edition');
    if (ed && EDITIONS[ed]) c = applyEdition(c, ed);
    const th = params.get('theme');
    if (th) c = { ...c, theme: { ...c.theme, preset: themePreset(th) } };
    if (params.get('screen') === 'print_home') c = { ...c, links: { ...c.links, print_home: 'https://liftpictures-fotos.de/plose/shop?code={code}' } };
    if (!params.has('preview')) c = { ...c, find: { ...c.find, scan: true } };
    if (params.get('lang')) c = { ...c, language: params.get('lang') as KioskConfig['language'] };
    return c;
  });
  const cfg = useMemo(() => (sim ? simCfg : mergeConfig(data.base, data.config)), [sim, simCfg, data.base, data.config]);
  // Nur die Geraete starten, die diese Einstellungen brauchen (Version: Karte, Bargeld, nur digital ...).
  const devices = useMemo(() => ({
    card: cfg.payments.card,
    cash: cfg.payments.cash,
    printer: cfg.products.print.enabled || cfg.products.combo.enabled,
    face: cfg.find.face,
  }), [cfg.payments.card, cfg.payments.cash, cfg.products.print.enabled, cfg.products.combo.enabled, cfg.find.face]);
  useEffect(() => { if (data.licensed && data.loaded) hw.configure(devices); }, [hw, devices, data.licensed, data.loaded]);
  const [tierSetting, setTierSetting] = useState<'auto' | Tier>((params.get('tier') as Tier) || 'auto');
  const tier = useTier(tierSetting !== 'auto' ? tierSetting : cfg.performance);
  const [frame, setFrame] = useState<Frame>((params.get('frame') as Frame) || 'fit');
  const vp = useViewport();
  // Vorschau im CRM/Dashboard: Einstellungen kommen per postMessage vom umgebenden Fenster.
  const preview = sim && params.has('preview');
  useEffect(() => {
    if (!preview) return;
    const on = (e: MessageEvent) => {
      const d = e.data as { type?: string; config?: unknown } | null;
      if (e.source === window.parent && e.origin === location.origin && d?.type === 'kiosk-preview') setSimCfg(mergeConfig(d.config));
    };
    window.addEventListener('message', on);
    window.parent?.postMessage({ type: 'kiosk-preview-ready' }, '*');
    return () => window.removeEventListener('message', on);
  }, [preview]);
  const panel = sim && !params.has('nopanel') && !preview;
  const availW = vp.w - (panel ? 320 : 0);

  // Buehne: im Automaten der ganze Bildschirm (ggf. gedreht), in der Demo wahlweise ein Quer-/Hochkant-Bildschirm.
  const rot = sim ? 0 : cfg.rotation;
  const side = rot === 90 || rot === 270;
  const W = frame === 'landscape' ? 1920 : frame === 'portrait' ? 1080 : side ? vp.h : availW;
  const H = frame === 'landscape' ? 1080 : frame === 'portrait' ? 1920 : side ? availW : vp.h;
  const scale = frame === 'fit' ? 1 : Math.min(availW / W, vp.h / H) * 0.96;
  useEffect(() => { document.documentElement.style.fontSize = `${Math.min(W, H) / 54}px`; }, [W, H]);
  useEffect(() => { document.body.classList.toggle('kiosk', !sim); }, [sim]);

  return (
    <>
      <div className={`stage${frame !== 'fit' ? ' framed' : ''}`} style={{ width: W, height: H, left: availW / 2, transform: `translate(-50%, -50%) rotate(${rot}deg) scale(${scale})` }}>
        <KioskProvider cfg={cfg} hw={hw} tier={tier} portrait={H > W} stageScale={scale} photos={data.photos}>
          {data.licensed ? <Shell /> : <BlockedShell reason={data.reason} />}
        </KioskProvider>
      </div>
      {panel && hw instanceof SimHardware && (
        <SimPanel hw={hw} cfg={simCfg} setCfg={setSimCfg} frame={frame} setFrame={setFrame} tier={tier} tierSetting={tierSetting} setTierSetting={setTierSetting} addPhoto={data.addSample} />
      )}
    </>
  );
}

function BlockedShell({ reason }: { reason?: string | null }) {
  const k = useKiosk();
  const th = THEMES[k.cfg.theme.preset] ?? THEMES.clean;
  return (
    <div className="app" style={themeStyle(k.cfg)} data-scheme={th.scheme} data-tier={k.tier}>
      <Blocked reason={reason} />
      <Overlays />
    </div>
  );
}
