// Bezahlen (Karte, Bargeld, Handy, Pass/Code) und Abschluss mit Druck und Download-Code.
// Grundsaetze: der Pfeil zeigt auf das echte Geraet, Betrag immer gross, Abbrechen jederzeit -
// eingeworfenes Geld kommt zurueck (oder bleibt als Guthaben, wenn der Automat kein Wechselgeld hat).
import { useCallback, useEffect, useRef, useState } from 'react';
import { photoFull } from '../data';
import { SimHardware } from '../hardware';
import { useKiosk } from '../store';
import { Bottom, DeviceArrow, Icon, Keypad, QR, Ring, Spinner } from '../ui';

type CardState = 'waiting' | 'processing' | 'approved' | 'declined' | 'timeout';
const CARD_SECONDS = 60;

export function CardPay() {
  const k = useKiosk();
  const { t } = k;
  const due = k.pricing.total;
  const [state, setState] = useState<CardState>('waiting');
  const [left, setLeft] = useState(CARD_SECONDS);
  const run = useRef(0);

  const start = useCallback(async () => {
    const id = ++run.current;
    setState('waiting');
    setLeft(CARD_SECONDS);
    const off = k.hw.on('card', (s) => { if (run.current === id && s === 'processing') setState('processing'); });
    const result = await k.hw.cardPay(due);
    off();
    if (run.current !== id) return;
    if (result === 'approved') { setState('approved'); window.setTimeout(() => k.finish('card'), 1200); }
    else if (result !== 'cancelled') setState(result === 'timeout' ? 'timeout' : 'declined');
  }, [due]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    k.setBusy(true);
    void start();
    return () => { run.current++; k.hw.cardCancel(); k.setBusy(false); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (state !== 'waiting') return;
    if (left <= 0) { run.current++; k.hw.cardCancel(); setState('timeout'); return; }
    const id = window.setTimeout(() => setLeft((l) => l - 1), 1000);
    return () => window.clearTimeout(id);
  }, [state, left]); // eslint-disable-line react-hooks/exhaustive-deps

  const failed = state === 'declined' || state === 'timeout';
  return (
    <div className="screen pay pay-card">
      <div className="pay-body">
        <div className={`terminal-art st-${state}`}>
          <div className="terminal">
            <div className="terminal-screen">
              {state === 'processing' ? <Spinner /> : state === 'approved' ? <Icon name="check" /> : failed ? <Icon name="x" /> : (
                <><b>{k.money(due)}</b><span className="contactless"><i /><i /><i /></span></>
              )}
            </div>
            <div className="terminal-keys">{Array.from({ length: 12 }, (_, i) => <i key={i} />)}</div>
          </div>
          {state === 'waiting' && <div className="tap-card"><Icon name="card" /></div>}
        </div>
        <div className="pay-info">
          <h1 className="title">{t('card.title', { x: k.money(due) })}</h1>
          {state === 'waiting' && <><p className="pay-lead">{t('card.tap')}</p><p className="sub">{t('card.follow')}</p></>}
          {state === 'processing' && <p className="pay-lead"><Spinner />{t('card.processing')}</p>}
          {state === 'approved' && <p className="pay-lead ok"><Icon name="check" />{t('card.approved')}</p>}
          {failed && (
            <div className="pay-fail">
              <p className="pay-lead bad"><Icon name="x" />{state === 'timeout' ? t('card.timeout') : t('card.declined')}</p>
              <p className="sub">{t('card.declined_sub')}</p>
              <div className="pay-actions">
                <button className="btn btn-primary btn-xl" onClick={() => void start()}>{t('card.retry')}</button>
                {k.methods.filter((m) => !m.disabled).length > 1 && <button className="btn btn-ghost btn-xl" onClick={() => k.go('method', { replace: true })}>{t('card.other')}</button>}
              </div>
            </div>
          )}
          {state === 'waiting' && left <= 20 && <p className="pay-warn"><Icon name="clock" />{t('card.warn', { s: left })}</p>}
        </div>
      </div>
      {(state === 'waiting' || state === 'processing') && <DeviceArrow pos={k.cfg.devices.card} label={t('card.where')} icon="card" />}
      <Bottom back={false}>
        {state !== 'approved' && state !== 'processing' && <button className="btn btn-ghost btn-xl" onClick={() => { run.current++; k.hw.cardCancel(); k.back(); }}>{t('common.cancel')}</button>}
      </Bottom>
    </div>
  );
}

export function CashPay() {
  const k = useKiosk();
  const { t, cfg } = k;
  const due = k.pricing.total;
  const [inserted, setInserted] = useState(k.credit);
  const [flash, setFlash] = useState(0);
  const [done, setDone] = useState(false);
  const [leaving, setLeaving] = useState<{ kind: 'refund' | 'credit'; cents: number } | null>(null);
  const givesChange = cfg.cash.gives_change && k.hwStatus.change;
  const sim = k.hw instanceof SimHardware ? k.hw : null;

  useEffect(() => {
    if (k.credit) k.setCredit(0);
    k.hw.cashEnable(Math.max(0, due - inserted));
    const off = k.hw.on('coin', (c) => { setInserted((v) => v + c); setFlash((f) => f + 1); });
    return () => { off(); k.hw.cashDisable(); k.setBusy(false); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { k.setBusy(inserted > 0 && !done); }, [inserted, done]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (done || inserted < due) return;
    setDone(true);
    k.hw.cashDisable();
    const change = inserted - due;
    void (async () => {
      // Was der Wechsler nicht herausgeben kann (Roehren leer), bleibt als Guthaben stehen.
      let returned = 0;
      if (change > 0 && givesChange) {
        returned = await k.hw.cashPayout(change);
        if (returned < change) k.setCredit(change - returned);
      } else if (change > 0) k.setCredit(change);
      window.setTimeout(() => k.finish('cash', returned), 1000);
    })();
  }, [inserted]); // eslint-disable-line react-hooks/exhaustive-deps

  async function cancel() {
    k.hw.cashDisable();
    if (inserted <= 0) { k.back(); return; }
    if (givesChange) {
      setLeaving({ kind: 'refund', cents: inserted });
      const back = await k.hw.cashPayout(inserted);
      if (back < inserted) { k.setCredit(inserted - back); setLeaving({ kind: 'credit', cents: inserted - back }); }
    } else { k.setCredit(inserted); setLeaving({ kind: 'credit', cents: inserted }); }
    setInserted(0);
    window.setTimeout(() => { k.setBusy(false); k.back(); }, 3200);
  }

  const leftToPay = Math.max(0, due - inserted);
  return (
    <div className="screen pay pay-cash">
      <div className="pay-body">
        <div className="cash-ring">
          <Ring value={due ? inserted / due : 1}>
            <small>{t('cash.paid')}</small>
            <b key={flash} className="bump">{k.money(inserted)}</b>
            <small>{k.money(due)}</small>
          </Ring>
        </div>
        <div className="pay-info">
          <h1 className="title">{done ? t('cash.complete') : t('cash.title', { x: k.money(leftToPay) })}</h1>
          {leaving ? (
            <p className="pay-lead ok"><Icon name="coins" />{leaving.kind === 'refund' ? t('cash.refund', { x: k.money(leaving.cents) }) : t('cash.credit', { x: k.money(leaving.cents) })}</p>
          ) : done ? (
            <p className="pay-lead ok"><Icon name="check" />{inserted > due && givesChange ? t('cash.change', { x: k.money(inserted - due) }) : t('cash.complete')}</p>
          ) : (
            <>
              <p className="pay-lead">{t('cash.insert')}</p>
              <div className="cash-rows">
                <div><span>{t('cash.paid')}</span><b>{k.money(inserted)}</b></div>
                <div className="strong"><span>{t('cash.left')}</span><b>{k.money(leftToPay)}</b></div>
              </div>
            </>
          )}
          {!givesChange && !done && !leaving && <p className="pay-warn"><Icon name="coins" />{t('cash.no_change')}</p>}
          <div className="denoms">
            <small>{t('cash.accepted')}</small>
            <div>
              {cfg.cash.denominations.map((d) => (
                <button key={d} className={`denom${d >= 500 ? ' note' : ''}`} disabled={!sim || done || !!leaving} onClick={() => sim?.insert(d)}>{k.money(d)}</button>
              ))}
            </div>
          </div>
        </div>
      </div>
      {!done && !leaving && <DeviceArrow pos={cfg.devices.cash} label={t('cash.where')} icon="coins" />}
      <Bottom back={false}>
        {!done && !leaving && <button className="btn btn-ghost btn-xl" onClick={() => void cancel()}>{t('common.cancel')}</button>}
      </Bottom>
    </div>
  );
}

/** Ein Link fuer alle Fotos, wenn die Kaufseite das kann ({codes}) - sonst ein QR-Code je Foto. */
export function useLinks(template: string, keys: string[]) {
  const k = useKiosk();
  const codes = keys.map((key) => k.byKey.get(key)?.code ?? key);
  if (codes.length <= 1 || template.includes('{codes}')) return [{ url: k.link(template, codes), key: keys[0] }];
  return codes.map((c, i) => ({ url: k.link(template, [c]), key: keys[i] }));
}

function QrList({ links, size }: { links: { url: string; key?: string }[]; size: string }) {
  const k = useKiosk();
  return (
    <div className="qr-list">
      {links.map((l, i) => {
        const p = l.key ? k.byKey.get(l.key) : undefined;
        return (
          <div className="qr-item" key={`${l.url}-${i}`}>
            <QR value={l.url} size={size} />
            {p && <span className="chip">{k.t('detail.number', { n: p.number })}</span>}
          </div>
        );
      })}
    </div>
  );
}

export function PhonePay() {
  const k = useKiosk();
  const { t } = k;
  const links = useLinks(k.cfg.links.phone_pay, k.cart.map((i) => i.key));
  useEffect(() => {
    let alive = true;
    k.setBusy(true);
    if (k.hw.phoneConfirms) void k.hw.phonePaid(links[0]?.url ?? '').then((ok) => { if (alive && ok) k.finish('phone'); });
    return () => { alive = false; k.hw.phoneCancel(); k.setBusy(false); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const single = links.length === 1;
  return (
    <div className="screen pay pay-phone">
      <div className={`pay-body${single ? '' : ' multi'}`}>
        {single
          ? <div className="phone-qr"><QR value={links[0].url} size="22rem" /><span className="phone-amount">{k.money(k.pricing.total)}</span></div>
          : <QrList links={links} size={links.length > 4 ? '9rem' : '12rem'} />}
        <div className="pay-info">
          <h1 className="title">{t('phone.title')}</h1>
          <ol className="phone-steps">
            <li><span>1</span>{single ? t('phone.s1') : t('phone.s1_each')}</li>
            <li><span>2</span>{t('phone.s2')}</li>
            <li><span>3</span>{t('phone.s3')}</li>
          </ol>
          {k.hw.phoneConfirms && <p className="pay-lead"><Spinner />{t('phone.waiting')}</p>}
        </div>
      </div>
      <Bottom back={false}>
        <button className="btn btn-ghost btn-xl" onClick={() => { k.hw.phoneCancel(); k.setBusy(false); k.back(); }}>{t('common.back')}</button>
        {!k.hw.phoneConfirms && <button className="btn btn-primary btn-xl" onClick={k.reset}>{t('phone.done')}<Icon name="check" /></button>}
      </Bottom>
    </div>
  );
}

// Tastatur wie gewohnt: QWERTZ auf Deutsch, sonst QWERTY. Ziffern 2-9 (Codes nutzen keine 0 und 1).
const keyboard = (de: boolean) => [
  (de ? 'QWERTZUIOP' : 'QWERTYUIOP').split(''),
  'ASDFGHJKL'.split(''),
  (de ? 'YXCVBNM' : 'ZXCVBNM').split(''),
  '23456789'.split(''),
  ['clr', 'del'],
];

export function VoucherScreen() {
  const k = useKiosk();
  const { t } = k;
  const [v, setV] = useState('');
  const [state, setState] = useState<'edit' | 'check' | 'bad' | 'ok'>('edit');
  const [msg, setMsg] = useState('');
  const press = (key: string) => {
    if (state === 'check' || state === 'ok') return;
    setState('edit');
    if (key === 'del') setV((x) => x.slice(0, -1));
    else if (key === 'clr') setV('');
    else setV((x) => (x + key).slice(0, 8));
  };
  async function redeem() {
    setState('check');
    const res = await k.hw.voucherCheck(v, k.cfg.vouchers.secret);
    if (!res) { setState('bad'); return; }
    k.setVoucher(res);
    setMsg(res.kind === 'day' ? t('voucher.day') : t('voucher.photos', { n: res.photos }));
    setState('ok');
    window.setTimeout(() => (k.cart.length ? k.go('cart', { replace: true }) : k.back()), 1800);
  }
  return (
    <div className="screen voucher">
      <div className="pad"><h1 className="title">{t('voucher.title')}</h1><p className="sub">{t('voucher.sub')}</p></div>
      <div className="voucher-body">
        <div className={`code-display${state === 'bad' ? ' shake' : ''}`}>
          {Array.from({ length: 8 }, (_, i) => <span key={i} className={v[i] ? 'f' : ''}>{v[i] ?? ''}</span>)}
        </div>
        <p className={`form-msg${state === 'bad' ? ' err' : state === 'ok' ? ' ok' : ''}`}>
          {state === 'bad' ? t('voucher.invalid') : state === 'ok' ? msg : ' '}
        </p>
        <Keypad rows={keyboard(k.lang === 'de')} onKey={press} wide />
      </div>
      <Bottom>
        <button className="btn btn-primary btn-xl" disabled={v.length < 8 || state === 'check' || state === 'ok'} onClick={() => void redeem()}>
          {state === 'check' ? <Spinner /> : <Icon name="ticket" />}{t('voucher.redeem')}
        </button>
      </Bottom>
    </div>
  );
}

export function Success() {
  const k = useKiosk();
  const { t } = k;
  const o = k.order;
  const prints = o ? o.items.filter((i) => i.format !== 'digital') : [];
  const digital = o ? o.items.filter((i) => i.format !== 'print') : [];
  const [print, setPrint] = useState<{ done: number; ok: boolean | null }>({ done: 0, ok: prints.length ? null : true });
  const [left, setLeft] = useState(45);

  useEffect(() => {
    if (!prints.length) return;
    const off = k.hw.on('print', (p) => setPrint((v) => ({ ...v, done: p.done })));
    const photos = prints.map((i) => k.byKey.get(i.key)).filter((p): p is NonNullable<typeof p> => !!p);
    void k.hw.print(photos, k.cfg.print).then((ok) => setPrint((v) => ({ ...v, ok })));
    return off;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (print.ok === null) return;
    if (left <= 0) { k.reset(); return; }
    const id = window.setTimeout(() => setLeft((l) => l - 1), 1000);
    return () => window.clearTimeout(id);
  }, [left, print.ok]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!o) return null;
  // Faellt der Drucker aus, bekommt der Gast seine Fotos digital.
  const downloadItems = print.ok === false ? o.items : digital;
  const first = k.byKey.get(o.items[0]?.key ?? '');
  return (
    <div className="screen success">
      {k.tier === 'high' && <div className="confetti" aria-hidden="true">{Array.from({ length: 28 }, (_, i) => <i key={i} style={{ left: `${(i * 37) % 100}%`, animationDelay: `${(i % 7) * 0.12}s` }} />)}</div>}
      <div className="success-head">
        <span className="success-check"><Icon name="check" /></span>
        <div>
          <h1 className="title">{t('success.title')}</h1>
          <p className="sub">{t('success.sub')}</p>
          {o.change > 0 && <p className="pay-lead ok"><Icon name="coins" />{t('success.change', { x: k.money(o.change) })}</p>}
        </div>
      </div>
      <div className="success-cards">
        {prints.length > 0 && (
          <div className={`s-card print ${print.ok === false ? 'bad' : ''}`}>
            {first && <img src={photoFull(first)} alt="" className={print.ok ? 'printed' : 'printing'} />}
            <div>
              <b>{print.ok === null ? t('success.printing') : print.ok ? t('success.printed') : t('success.print_error')}</b>
              {print.ok === null && <div className="bar"><i style={{ width: `${Math.round(((print.done + 0.5) / prints.length) * 100)}%` }} /></div>}
            </div>
          </div>
        )}
        {downloadItems.length > 0 && (
          <div className="s-card digital">
            <DownloadQr keys={downloadItems.map((i) => i.key)} />
            <div><b>{t('success.digital')}</b><small>{t('common.photos', { n: downloadItems.length })}</small></div>
          </div>
        )}
      </div>
      {prints.length > 0 && print.ok !== false && <DeviceArrow pos={k.cfg.devices.printer} label={t('success.print_where')} icon="printer" />}
      <Bottom back={false}>
        <span className="muted">{t('success.back', { s: left })}</span>
        <button className="btn btn-primary btn-xl" onClick={k.reset}>{t('common.done')}<Icon name="check" /></button>
      </Bottom>
    </div>
  );
}

function DownloadQr({ keys }: { keys: string[] }) {
  const k = useKiosk();
  const links = useLinks(k.cfg.links.download, keys);
  return links.length === 1 ? <QR value={links[0].url} size="13rem" /> : <QrList links={links} size={links.length > 3 ? '7rem' : '9rem'} />;
}
