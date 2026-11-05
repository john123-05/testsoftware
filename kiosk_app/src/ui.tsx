// Gemeinsame Bausteine: Symbole, Kopf- und Fusszeile, QR-Code, Tastenfeld, Fortschrittsring, Geraete-Pfeil.
import { useEffect, useRef, useState, type ReactNode } from 'react';
import QRCode from 'qrcode';
import { LANGS, type Pos } from './config';
import { PAY_SCREENS, useKiosk } from './store';

const ICONS = {
  search: '<circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4.6-4.6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
  scan: '<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><circle cx="9.2" cy="10" r=".9" fill="currentColor"/><circle cx="14.8" cy="10" r=".9" fill="currentColor"/><path d="M9 14.5c1.7 1.4 4.3 1.4 6 0"/>',
  hash: '<path d="M4.5 9h15M4.5 15h15M10 4 8 20M16 4l-2 16"/>',
  phone: '<rect x="6.5" y="2.5" width="11" height="19" rx="2.5"/><path d="M11 18.2h2"/>',
  ticket: '<path d="M4 7.5A1.5 1.5 0 0 1 5.5 6h13A1.5 1.5 0 0 1 20 7.5V10a2 2 0 0 0 0 4v2.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 16.5V14a2 2 0 0 0 0-4z"/><path d="M14 6.5v2M14 11v2M14 15.5v2"/>',
  card: '<rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M2.5 10h19M6.5 15h4"/>',
  coins: '<circle cx="9" cy="9" r="6"/><path d="M15.6 9.2a6 6 0 1 1-6.4 6.4"/><path d="M8 7.2h1.5V11"/>',
  printer: '<path d="M6.5 9V3.5h11V9"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M6.5 14h11v6.5h-11z"/>',
  delivery: '<path d="M2 6h13v11H2zM15 10h4l3 3v4h-7"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
  combo: '<path d="M14 3H4v14h10M7 7h4m-4 4h3"/><rect x="13" y="7" width="7" height="14" rx="2"/><path d="M16 18h1"/>',
  download: '<path d="M12 3.5v11m-4.5-4.5L12 14.5 16.5 10M4 20.5h16"/>',
  check: '<path d="m5 12.5 4.5 4.5L19.5 7"/>',
  x: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
  left: '<path d="m14.5 18-6-6 6-6"/>',
  right: '<path d="m9.5 18 6-6-6-6"/>',
  down: '<path d="M12 4v15m-6.5-6.5L12 19l6.5-6.5"/>',
  home: '<path d="M3.5 11 12 3.5l8.5 7.5"/><path d="M5.5 9.5v10h13v-10"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.3a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .8-1 1.6M12 16.8h.01"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.7 5.6 3.7 9s-1.2 6.4-3.7 9c-2.5-2.6-3.7-5.6-3.7-9S9.5 5.6 12 3z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  cart: '<path d="M3 4h2.2l2.3 10.5h10.8L21 7.2H6.3"/><circle cx="9.5" cy="19" r="1.6"/><circle cx="17" cy="19" r="1.6"/>',
  sparkle: '<path d="M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1L5 10.5l5.1-1.9z"/><path d="M18.5 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
  pin: '<path d="M12 21s-6.5-5.8-6.5-10.7a6.5 6.5 0 0 1 13 0C18.5 15.2 12 21 12 21z"/><circle cx="12" cy="10.3" r="2.4"/>',
  camera: '<path d="M4 8.5h3l1.8-2.8h6.4L17 8.5h3V19H4z"/><circle cx="12" cy="13.2" r="3.4"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  trash: '<path d="M4.5 7h15M10 11v6M14 11v6M6.5 7l.9 13h9.2l.9-13M9.5 7V4.5h5V7"/>',
  image: '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.8"/><path d="m21 16-5-5-8.5 8.5"/>',
  bolt: '<path d="M13 2.5 4.5 13.5H12l-1 8 8.5-11H12z"/>',
  backspace: '<path d="M9 5h11a1.5 1.5 0 0 1 1.5 1.5v11A1.5 1.5 0 0 1 20 19H9l-6-7z"/><path d="m11.5 9.5 5 5M16.5 9.5l-5 5"/>',
};
export type IconName = keyof typeof ICONS;

export function Icon({ name, className = '' }: { name: IconName; className?: string }) {
  return (
    <svg className={`ic ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" dangerouslySetInnerHTML={{ __html: ICONS[name] }} />
  );
}

export function QR({ value, size = '12rem' }: { value: string; size?: string }) {
  const [svg, setSvg] = useState('');
  useEffect(() => {
    let alive = true;
    if (!value) { setSvg(''); return; }
    void QRCode.toString(value, { type: 'svg', margin: 1, errorCorrectionLevel: 'M', color: { dark: '#0b1220', light: '#ffffff' } })
      .then((s) => { if (alive) setSvg(s); }).catch(() => { if (alive) setSvg(''); });
    return () => { alive = false; };
  }, [value]);
  return <div className="qr" style={{ width: size, height: size }} dangerouslySetInnerHTML={{ __html: svg }} />;
}

/** Logo des Parks. Personal: 2,5 Sekunden gedrueckt halten oeffnet das Personal-Menue. */
export function Logo({ admin = false }: { admin?: boolean }) {
  const k = useKiosk();
  const timer = useRef(0);
  const down = () => { if (admin) timer.current = window.setTimeout(() => k.setOverlay('admin'), 2500); };
  const up = () => window.clearTimeout(timer.current);
  const initials = k.cfg.park_name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
  return (
    <div className="logo" onPointerDown={down} onPointerUp={up} onPointerLeave={up}>
      {k.cfg.theme.logo ? <img src={k.cfg.theme.logo} alt="" /> : <span className="logo-mark">{initials}</span>}
      <span className="logo-text"><b>{k.cfg.park_name}</b><small>Liftpictures</small></span>
    </div>
  );
}

export function TopBar() {
  const k = useKiosk();
  const lang = LANGS.find((l) => l.id === k.lang);
  const showCart = k.cart.length > 0 && !['cart', 'method', 'success', ...PAY_SCREENS].includes(k.screen);
  return (
    <header className="top">
      <Logo admin />
      <div className="top-right">
        {showCart && (
          <button className="cart-pill" disabled={k.busy} onClick={() => k.go('cart')}>
            <Icon name="cart" /><b>{k.cart.length}</b><span>{k.money(k.pricing.total)}</span>
          </button>
        )}
        {k.cfg.languages.length > 1 && (
          <button className="icon-btn" onClick={() => k.setOverlay('lang')} disabled={k.busy}>
            <Icon name="globe" /><span>{lang?.code}</span>
          </button>
        )}
        <button className="icon-btn" onClick={() => k.setOverlay('help')}><Icon name="help" /><span>{k.t('common.help')}</span></button>
        {k.screen !== 'success' && (
          <button className="icon-btn" onClick={k.restart} disabled={k.busy}><Icon name="home" /><span>{k.t('common.start_over')}</span></button>
        )}
      </div>
    </header>
  );
}

/** Fusszeile: Zurueck immer links, die Hauptaktion immer rechts - an jedem Bildschirm an derselben Stelle. */
export function Bottom({ back = true, onBack, children }: { back?: boolean; onBack?: () => void; children?: ReactNode }) {
  const k = useKiosk();
  return (
    <footer className="bottom">
      {back && (
        <button className="btn btn-ghost btn-back" disabled={k.busy} onClick={onBack ?? k.back}>
          <Icon name="left" />{k.t('common.back')}
        </button>
      )}
      <div className="grow" />
      {children}
    </footer>
  );
}

export function Keypad({ rows, onKey, wide = false }: { rows: string[][]; onKey: (key: string) => void; wide?: boolean }) {
  return (
    <div className={`keypad${wide ? ' wide' : ''}`}>
      {rows.map((row, i) => (
        <div className="keypad-row" key={i}>
          {row.map((key) => (
            <button key={key} className={`key${key.length > 1 ? ' key-fn' : ''}`} onClick={() => onKey(key)}>
              {key === 'del' ? <Icon name="backspace" /> : key === 'clr' ? 'C' : key}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

export function Ring({ value, children, size = '17rem' }: { value: number; children?: ReactNode; size?: string }) {
  const r = 44, c = 2 * Math.PI * r;
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} className="ring-track" />
        <circle cx="50" cy="50" r={r} className="ring-bar" strokeDasharray={c} strokeDashoffset={c * (1 - Math.max(0, Math.min(1, value)))} />
      </svg>
      <div className="ring-body">{children}</div>
    </div>
  );
}

/** Zeigt auf das echte Geraet am Automaten (Kartenterminal, Muenzschlitz, Fotoausgabe). */
export function DeviceArrow({ pos, label, icon }: { pos: Pos; label: string; icon: IconName }) {
  return (
    <div className={`device-arrow pos-${pos}`}>
      <span className="da-label"><Icon name={icon} />{label}</span>
      <span className="da-arrow"><Icon name="down" /></span>
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}
