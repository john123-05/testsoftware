// Simulator-Feld (nur im Browser/Demo): Version, Bildschirm, Farbwelt, Leistung und Geraete ausloesen.
import { useState } from 'react';
import { EDITIONS, THEMES, applyEdition, editionOf, type KioskConfig, type Tier } from './config';
import type { SimHardware } from './hardware';

export type Frame = 'fit' | 'landscape' | 'portrait';

export function SimPanel({ hw, cfg, setCfg, frame, setFrame, tier, tierSetting, setTierSetting, addPhoto }: {
  hw: SimHardware; cfg: KioskConfig; setCfg: (c: KioskConfig) => void;
  frame: Frame; setFrame: (f: Frame) => void;
  tier: Tier; tierSetting: 'auto' | Tier; setTierSetting: (t: 'auto' | Tier) => void;
  addPhoto: () => void;
}) {
  const [open, setOpen] = useState(true);
  const [, force] = useState(0);
  const refresh = () => force((x) => x + 1);
  const money = (c: number) => new Intl.NumberFormat('de-DE', { style: 'currency', currency: cfg.currency }).format(c / 100);
  if (!open) return <button className="sim-open" onClick={() => setOpen(true)}>Simulator</button>;
  return (
    <aside className="sim">
      <header><b>Simulator</b><span>Liftpictures Kiosk</span><button onClick={() => setOpen(false)}>×</button></header>
      <label>Version
        <select value={editionOf(cfg) ?? ''} onChange={(e) => setCfg(applyEdition(cfg, e.target.value))}>
          {!editionOf(cfg) && <option value="">Eigene</option>}
          {Object.entries(EDITIONS).map(([id, e]) => <option key={id} value={id}>{e.label}</option>)}
        </select>
      </label>
      <label>Bildschirm
        <div className="seg">
          {(['fit', 'landscape', 'portrait'] as Frame[]).map((f) => (
            <button key={f} className={frame === f ? 'on' : ''} onClick={() => setFrame(f)}>{f === 'fit' ? 'Fenster' : f === 'landscape' ? 'Quer' : 'Hochkant'}</button>
          ))}
        </div>
      </label>
      <label>Farbwelt
        <select value={cfg.theme.preset} onChange={(e) => setCfg({ ...cfg, theme: { ...cfg.theme, preset: e.target.value } })}>
          {Object.entries(THEMES).map(([id, th]) => <option key={id} value={id}>{th.label}</option>)}
        </select>
      </label>
      <label>Leistung des PCs <em>jetzt: {tier}</em>
        <div className="seg">
          {(['auto', 'low', 'mid', 'high'] as const).map((t) => <button key={t} className={tierSetting === t ? 'on' : ''} onClick={() => setTierSetting(t)}>{t}</button>)}
        </div>
      </label>
      <label className="check"><input type="checkbox" checked={cfg.express} onChange={(e) => setCfg({ ...cfg, express: e.target.checked })} />Hochbetrieb (Format überspringen)</label>
      <label className="check"><input type="checkbox" checked={hw.auto} onChange={(e) => { hw.auto = e.target.checked; refresh(); }} />Zahlungen automatisch bestätigen</label>
      <div className="sim-group">
        <small>Münzen / Scheine einwerfen</small>
        <div className="sim-coins">{cfg.cash.denominations.map((d) => <button key={d} onClick={() => hw.insert(d)}>{money(d)}</button>)}</div>
        <label className="check"><input type="checkbox" checked={cfg.cash.gives_change} onChange={(e) => setCfg({ ...cfg, cash: { ...cfg.cash, gives_change: e.target.checked } })} />Gibt Wechselgeld</label>
      </div>
      <div className="sim-group">
        <small>Kartenterminal</small>
        <div className="sim-row"><button onClick={() => hw.simCard('approved')}>Karte OK</button><button onClick={() => hw.simCard('declined')}>Abgelehnt</button></div>
      </div>
      <div className="sim-group">
        <small>Handy-Zahlung · Drucker · Gesicht</small>
        <div className="sim-row">
          <button onClick={() => hw.simPhone(true)}>Handy bezahlt</button>
          <button onClick={() => { hw.setStatus({ printer: hw.status.printer === 'paper_out' ? 'ready' : 'paper_out' }); refresh(); }}>
            {hw.status.printer === 'paper_out' ? 'Papier nachfüllen' : 'Papier leer'}
          </button>
        </div>
        <label className="check"><input type="checkbox" checked={hw.faceFinds} onChange={(e) => { hw.faceFinds = e.target.checked; refresh(); }} />Gesichtssuche findet Fotos</label>
        <button className="sim-wide" onClick={addPhoto}>Neues Foto (jemand fährt gerade)</button>
      </div>
      <p className="sim-note">Codes: <b>DAYPASS2</b> = Tagespass, <b>P2FREE22</b> = 2 Gratis-Fotos. Personal-Menü: Logo 2,5 s halten, PIN <b>{cfg.admin_pin}</b>.</p>
    </aside>
  );
}
