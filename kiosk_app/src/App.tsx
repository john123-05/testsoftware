// Liftpictures Kiosk - neues Verkaufsprogramm fuer Fotoautomaten.
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { DEFAULT_CONFIG, EDITIONS, THEMES, applyEdition, mergeConfig, type KioskConfig, type Tier } from './config';
import { createHardware, SimHardware } from './hardware';
import { useKioskData } from './data';
import { useTier } from './perf';
import { KioskProvider, useKiosk, type Screen } from './store';
import { TopBar } from './ui';
import { Overlays, Blocked } from './overlays';
import { SimPanel, type Frame } from './SimPanel';
import { Attract, FaceScreen, Home, NumberScreen, TimeScreen } from './screens/Start';
import { Detail, Gallery } from './screens/Browse';
import { Cart, Method, Products } from './screens/Buy';
import { CardPay, CashPay, PhonePay, Success, VoucherScreen } from './screens/Pay';

const SCREENS: Record<Screen, () => JSX.Element | null> = {
  attract: Attract, home: Home, time: TimeScreen, gallery: Gallery, detail: Detail, number: NumberScreen, face: FaceScreen,
  products: Products, cart: Cart, method: Method, card: CardPay, cash: CashPay, phone: PhonePay, voucher: VoucherScreen, success: Success,
};

function themeStyle(cfg: KioskConfig): CSSProperties {
  const th = THEMES[cfg.theme.preset] ?? THEMES.alpine;
  const vars: Record<string, string> = {
    '--bg': th.bg, '--bg2': th.bg2, '--surface': th.surface, '--surface2': th.surface2, '--line': th.line,
    '--text': th.text, '--muted': th.muted, '--brand': cfg.theme.brand || th.brand, '--brandInk': th.brandInk,
    '--accent': cfg.theme.accent || th.accent, '--accentInk': th.accentInk,
  };
  if (cfg.theme.background) vars['--bgImage'] = cfg.theme.background.startsWith('http') || cfg.theme.background.startsWith('data:') ? `url("${cfg.theme.background}")` : cfg.theme.background;
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
  useEffect(() => { last.current = Date.now(); }, [k.screen]);
  useEffect(() => {
    const id = window.setInterval(() => {
      if (k.screen === 'attract' || k.screen === 'success' || k.busy || k.overlay === 'idle' || k.overlay === 'admin') return;
      if (Date.now() - last.current > k.cfg.idle_seconds * 1000) k.setOverlay('idle');
    }, 1000);
    return () => window.clearInterval(id);
  }, [k.screen, k.busy, k.overlay, k.cfg.idle_seconds]); // eslint-disable-line react-hooks/exhaustive-deps
}

function Shell() {
  const k = useKiosk();
  useIdle();
  const View = SCREENS[k.screen];
  const th = THEMES[k.cfg.theme.preset] ?? THEMES.alpine;
  return (
    <div className={`app ${k.portrait ? 'portrait' : 'landscape'}`} style={themeStyle(k.cfg)} data-scheme={th.scheme}>
      {k.screen !== 'attract' && <TopBar />}
      <main className="main"><View key={k.screen === 'detail' ? `detail-${k.detail}` : k.screen} /></main>
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
    if (th && THEMES[th]) c = { ...c, theme: { ...c.theme, preset: th } };
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
  useEffect(() => { if (data.licensed) hw.configure(devices); }, [hw, devices, data.licensed]);
  const [tierSetting, setTierSetting] = useState<'auto' | Tier>((params.get('tier') as Tier) || 'auto');
  const tier = useTier(tierSetting !== 'auto' ? tierSetting : cfg.performance);
  const [frame, setFrame] = useState<Frame>((params.get('frame') as Frame) || 'fit');
  const vp = useViewport();
  const panel = sim && !params.has('nopanel');
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
  const th = THEMES[k.cfg.theme.preset] ?? THEMES.alpine;
  return (
    <div className="app" style={themeStyle(k.cfg)} data-scheme={th.scheme}>
      <Blocked reason={reason} />
      <Overlays />
    </div>
  );
}
