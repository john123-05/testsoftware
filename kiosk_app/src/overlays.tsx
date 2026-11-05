// Einblendungen: Hilfe, "Auf dem Handy suchen", "Bist du noch da?", Sprache, Personal-Menue, nicht freigeschaltet.
import { useEffect, useState } from 'react';
import { IDLE_WARNING_SECONDS, LANGS } from './config';
import { SimHardware } from './hardware';
import { salesToday, useKiosk, type Screen } from './store';
import { Icon, Keypad, Logo, QR } from './ui';

const HELP_GROUP: Partial<Record<Screen, string>> = {
  gallery: 'gallery', detail: 'detail', products: 'cart', cart: 'cart',
  method: 'pay', card: 'pay', cash: 'pay', phone: 'pay', voucher: 'pay',
};

function Help() {
  const k = useKiosk();
  const steps = k.t(`help.${HELP_GROUP[k.screen] ?? 'home'}`).split('|');
  return (
    <div className="modal" onClick={(e) => e.stopPropagation()}>
      <h2><Icon name="help" />{k.t('help.title')}</h2>
      <ol className="help-steps">{steps.map((s, i) => <li key={i}><span>{i + 1}</span>{s}</li>)}</ol>
      <p className="modal-note">{k.t('help.staff')}</p>
      {k.cfg.find.phone && k.cfg.links.phone_search && ['gallery', 'detail', 'number', 'face', 'scan'].includes(k.screen) &&
        <button className="btn btn-ghost full" onClick={() => k.setOverlay('handoff')}><Icon name="phone" />{k.t('home.phone')}</button>}
      <button className="btn btn-primary btn-xl full" onClick={() => k.setOverlay(null)}>{k.t('common.close')}</button>
    </div>
  );
}

function Handoff() {
  const k = useKiosk();
  return (
    <div className="modal modal-qr" onClick={(e) => e.stopPropagation()}>
      <QR value={k.link(k.cfg.links.phone_search, [], k.search.time)} size="20rem" />
      <div>
        <h2><Icon name="phone" />{k.t('handoff.title')}</h2>
        <p className="modal-text">{k.t('handoff.sub')}</p>
        <button className="btn btn-primary btn-xl full" onClick={() => k.setOverlay(null)}>{k.t('common.close')}</button>
      </div>
    </div>
  );
}

function Idle() {
  const k = useKiosk();
  const [left, setLeft] = useState(IDLE_WARNING_SECONDS);
  useEffect(() => {
    if (left <= 0) { k.reset(); return; }
    const id = window.setTimeout(() => setLeft((l) => l - 1), 1000);
    return () => window.clearTimeout(id);
  }, [left]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="modal modal-idle" onClick={(e) => e.stopPropagation()}>
      <h2>{k.t('idle.title')}</h2>
      <p className="modal-text">{k.t('idle.sub', { s: left })}</p>
      <div className="modal-actions">
        <button className="btn btn-ghost btn-xl" onClick={k.reset}>{k.t('common.start_over')}</button>
        <button className="btn btn-primary btn-xl" onClick={() => k.setOverlay(null)}>{k.t('idle.continue')}</button>
      </div>
    </div>
  );
}

function Lang() {
  const k = useKiosk();
  return (
    <div className="modal" onClick={(e) => e.stopPropagation()}>
      <h2><Icon name="globe" />Language · Sprache</h2>
      <div className="lang-grid">
        {LANGS.filter((l) => k.cfg.languages.includes(l.id)).map((l) => (
          <button key={l.id} className={`lang-btn${l.id === k.lang ? ' on' : ''}`} onClick={() => { k.setLang(l.id); k.setOverlay(null); }}>
            <b>{l.code}</b><span>{l.name}</span>{l.id === k.lang && <Icon name="check" />}
          </button>
        ))}
      </div>
    </div>
  );
}

function Admin() {
  const k = useKiosk();
  const [pin, setPin] = useState('');
  const [ok, setOk] = useState(false);
  const [wrong, setWrong] = useState(false);
  const press = (key: string) => {
    setWrong(false);
    const next = key === 'del' ? pin.slice(0, -1) : key === 'clr' ? '' : (pin + key).slice(0, 6);
    setPin(next);
    if (next.length === k.cfg.admin_pin.length) {
      if (next === k.cfg.admin_pin) setOk(true); else { setWrong(true); setPin(''); }
    }
  };
  if (!ok) {
    return (
      <div className="modal modal-pin" onClick={(e) => e.stopPropagation()}>
        <h2><Icon name="lock" />{k.t('admin.pin')}</h2>
        <div className={`code-display small${wrong ? ' shake' : ''}`}>{Array.from({ length: k.cfg.admin_pin.length }, (_, i) => <span key={i} className={pin[i] ? 'f' : ''}>{pin[i] ? '•' : ''}</span>)}</div>
        <p className={`form-msg${wrong ? ' err' : ''}`}>{wrong ? k.t('admin.wrong') : ' '}</p>
        <Keypad rows={[['1', '2', '3'], ['4', '5', '6'], ['7', '8', '9'], ['clr', '0', 'del']]} onKey={press} />
        <button className="btn btn-ghost btn-xl full" onClick={() => k.setOverlay(null)}>{k.t('common.close')}</button>
      </div>
    );
  }
  const sales = salesToday();
  const total = sales.reduce((s, x) => s + x.total, 0);
  const st = k.hwStatus;
  const devices: [string, boolean, string][] = [
    [k.t('dev.card'), st.card, st.card ? 'OK' : '–'],
    [k.t('dev.cash'), st.cash, st.cash ? 'OK' : '–'],
    [k.t('dev.change'), st.change, st.change ? 'OK' : '–'],
    [k.t('dev.printer'), st.printer === 'ready' || st.printer === 'printing', st.printer],
    [k.t('dev.face'), st.face, st.face ? 'OK' : '–'],
  ];
  return (
    <div className="modal modal-admin" onClick={(e) => e.stopPropagation()}>
      <h2><Icon name="lock" />{k.t('admin.title')}</h2>
      <div className="admin-grid">
        <div className="admin-box">
          <small>{k.t('admin.sales')}</small>
          <b>{k.money(total)}</b>
          <span>{k.t('admin.orders', { n: sales.length })}</span>
        </div>
        <div className="admin-box">
          <small>{k.t('admin.devices')}</small>
          {devices.map(([name, good, label]) => <div key={name} className="admin-dev"><i className={good ? 'ok' : 'bad'} />{name}<em>{label}</em></div>)}
        </div>
      </div>
      <p className="modal-note">Liftpictures Kiosk · {k.hw.mode === 'sim' ? 'Simulator' : 'Liftpictures Display'} · {k.tier}</p>
      <div className="modal-actions">
        <button className="btn btn-ghost btn-xl" onClick={() => { const p = k.today[0]; if (p) void k.hw.print([p], k.cfg.print); }}><Icon name="printer" />{k.t('admin.test_print')}</button>
        {!(k.hw instanceof SimHardware) && <button className="btn btn-ghost btn-xl" onClick={() => k.hw.exit()}>{k.t('admin.exit')}</button>}
        <button className="btn btn-primary btn-xl" onClick={() => k.setOverlay(null)}>{k.t('common.close')}</button>
      </div>
    </div>
  );
}

export function Overlays() {
  const k = useKiosk();
  if (!k.overlay) return null;
  const dismissable = k.overlay !== 'idle' && k.overlay !== 'admin';
  return (
    <div className="scrim" onClick={() => dismissable && k.setOverlay(null)}>
      {k.overlay === 'help' && <Help />}
      {k.overlay === 'handoff' && <Handoff />}
      {k.overlay === 'idle' && <Idle />}
      {k.overlay === 'lang' && <Lang />}
      {k.overlay === 'admin' && <Admin />}
    </div>
  );
}

export function Blocked({ reason }: { reason?: string | null }) {
  const k = useKiosk();
  return (
    <div className="blocked">
      <Logo admin />
      <span className="blocked-icon"><Icon name="lock" /></span>
      <h1 className="title">{k.t('blocked.title')}</h1>
      {reason && k.t(`blocked.r_${reason}`) !== `blocked.r_${reason}` && <p className="pay-lead">{k.t(`blocked.r_${reason}`)}</p>}
      <p className="sub">{k.t('blocked.sub')}{reason ? ` (${reason})` : ''}</p>
    </div>
  );
}
