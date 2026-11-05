// Fotos durchsehen: Raster mit Zeitleiste, Groesse per + / − oder zwei Fingern, "Hier warst du"-Markierung,
// Hilfe-Hinweise wenn jemand lange sucht, und die Grossansicht mit Zoom.
import { useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent } from 'react';
import { photoFull, photoSrc, type Photo } from '../data';
import { useKiosk } from '../store';
import { Bottom, Icon } from '../ui';

const BUCKET = 900; // Viertelstunde

function groupPhotos(list: Photo[]) {
  const groups: { start: number; photos: Photo[] }[] = [];
  for (const p of list) {
    const start = Math.floor(p.ts / BUCKET) * BUCKET;
    const last = groups[groups.length - 1];
    if (last && last.start === start) last.photos.push(p); else groups.push({ start, photos: [p] });
  }
  return groups;
}

export function Gallery() {
  const k = useKiosk();
  const { cfg, t, search } = k;
  const now = Date.now() / 1000;
  const recent = useMemo(() => k.today.filter((p) => p.ts >= now - cfg.find.just_rode_minutes * 60), [k.today, cfg.find.just_rode_minutes]); // eslint-disable-line react-hooks/exhaustive-deps
  const fallback = search.mode === 'recent' && recent.length === 0;
  const list = useMemo(() => {
    if (search.mode === 'face') return k.photos.filter((p) => search.faceKeys?.includes(p.key));
    if (search.mode === 'recent') return recent.length ? recent : k.today.slice(0, 24);
    return k.today;
  }, [search, recent, k.today, k.photos]);
  const groups = useMemo(() => groupPhotos(list), [list]);
  const target = search.mode === 'time' ? search.time ?? null : null;
  const targetGroup = target == null ? null : Math.floor(target / BUCKET) * BUCKET;
  const [cols, setCols] = useState(() => (cfg.express ? (k.portrait ? 2 : 4) : k.portrait ? 3 : 5));
  const scroller = useRef<HTMLDivElement>(null);
  const hours = useMemo(() => {
    const byHour = new Map<number, number>();
    for (const photo of k.today) {
      const d = new Date(photo.ts * 1000);
      d.setMinutes(0, 0, 0);
      if (!byHour.has(d.getTime())) byHour.set(d.getTime(), photo.ts);
    }
    return [...byHour.entries()];
  }, [k.today]);

  useEffect(() => {
    const box = scroller.current;
    if (!box) return;
    const group = targetGroup == null ? null : document.getElementById(`g${targetGroup}`);
    box.scrollTop = group?.offsetTop ?? 0;
  }, [targetGroup, search.mode]);

  // Zwei Finger: Fotos groesser/kleiner (wie auf dem Handy).
  const pts = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<{ d: number; cols: number } | null>(null);
  const dist = () => { const a = [...pts.current.values()]; return a.length < 2 ? 0 : Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y); };
  const down = (e: RPointerEvent) => { pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY }); if (pts.current.size === 2) pinch.current = { d: dist(), cols }; };
  const move = (e: RPointerEvent) => {
    if (!pts.current.has(e.pointerId)) return;
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch.current && pts.current.size === 2 && pinch.current.d > 0) {
      const next = Math.round(pinch.current.cols / (dist() / pinch.current.d));
      setCols(Math.max(1, Math.min(7, next)));
    }
  };
  const up = (e: RPointerEvent) => { pts.current.delete(e.pointerId); if (pts.current.size < 2) pinch.current = null; };

  const title = search.mode === 'face' ? t('gallery.face', { n: list.length })
    : search.mode === 'recent' ? t('gallery.recent', { n: cfg.find.just_rode_minutes })
      : search.mode === 'time' && target ? t('gallery.time', { time: k.time(target) }) : t('gallery.all');
  const keys = useMemo(() => list.map((p) => p.key), [list]);
  const inCart = useMemo(() => new Set(k.cart.map((i) => i.key)), [k.cart]);

  return (
    <div className="screen gallery">
      <div className="gallery-filters">
        <button className="btn btn-ghost" aria-pressed={search.mode === 'recent'} onClick={() => k.find({ mode: 'recent' })}>{t('home.just_rode')}</button>
        <button className="btn btn-ghost" aria-pressed={search.mode === 'all'} onClick={() => k.find({ mode: 'all' })}>{t('gallery.show_all')}</button>
        {cfg.find.number && <button className="btn btn-ghost" onClick={() => k.go('number')}>{t('home.number')}</button>}
        {cfg.find.face && k.hwStatus.face && <button className="btn btn-ghost" onClick={() => k.go('face')}>{t('home.face')}</button>}
        {cfg.find.scan && <button className="btn btn-ghost" onClick={() => k.go('scan')}><Icon name="scan" />{t('scan.title')}</button>}
        {cfg.payments.voucher && !cfg.find.scan && <button className="btn btn-ghost" onClick={() => k.go('voucher')}>{t('home.voucher')}</button>}
        {k.voucher && <span className="chip chip-ok">{k.voucher.kind === 'day' ? t('voucher.day') : t('voucher.photos', { n: k.voucher.photos })}</span>}
      </div>
      {cfg.find.time && hours.length > 0 && <div className="gallery-hours" aria-label={t('home.time')}>
        {hours.map(([hour, ts]) => <button className="btn btn-ghost" key={hour} aria-pressed={target === ts} onClick={() => k.find({ mode: 'time', time: ts })}>{k.time(hour / 1000)}</button>)}
      </div>}
      <div className="gal-head">
        <h1 className="title sm">{title}</h1>
        {fallback && <p className="sub">{t('gallery.fallback')}</p>}
        <div className="zoom-ctl" aria-label={t('gallery.size')}>
          <button onClick={() => setCols((c) => Math.min(7, c + 1))} aria-label="−"><Icon name="minus" /></button>
          <button onClick={() => setCols((c) => Math.max(1, c - 1))} aria-label="+"><Icon name="plus" /></button>
        </div>
      </div>
      <div className="gal-scroll" ref={scroller} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
        {groups.map((g) => (
          <section key={g.start} id={`g${g.start}`} className={`gal-group${g.start === targetGroup ? ' target' : ''}`}>
            <h4 className="gal-time">
              <span>{k.time(g.start)}</span>
              {g.start === targetGroup && <span className="you-pill"><Icon name="pin" />{t('gallery.you')}</span>}
              <small>{t('common.photos', { n: g.photos.length })}</small>
            </h4>
            <div className="gal-grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
              {g.photos.map((p) => (
                <button key={p.key} className={`thumb${inCart.has(p.key) ? ' in-cart' : ''}${target != null && Math.abs(p.ts - target) <= 240 ? ' near' : ''}`}
                  onClick={() => k.openDetail(p.key, keys)}>
                  <img src={photoSrc(p)} alt="" loading="lazy" decoding="async" />
                  <span className="thumb-meta"><b>{p.number}</b><span>{k.time(p.ts)}</span></span>
                  {inCart.has(p.key) && <span className="thumb-badge"><Icon name="check" /></span>}
                </button>
              ))}
            </div>
          </section>
        ))}
        {!list.length && <div className="empty"><Icon name="image" />{t('gallery.empty')}</div>}
      </div>
      {k.cart.length > 0 && <Bottom back={false}>
          <button className="btn btn-primary btn-xl" onClick={() => k.go('cart')}><Icon name="cart" />{k.t('detail.to_cart')} · {k.money(k.pricing.total)}</button>
      </Bottom>}
    </div>
  );
}

function ZoomImage({ src, onSwipe }: { src: string; onSwipe: (dir: 1 | -1) => void }) {
  const k = useKiosk();
  const [z, setZ] = useState({ s: 1, x: 0, y: 0 });
  const pts = useRef(new Map<number, { x: number; y: number }>());
  const start = useRef<{ d: number; s: number; x: number; y: number; cx: number; cy: number } | null>(null);
  const lastTap = useRef(0);
  const zRef = useRef(z);
  zRef.current = z;
  const snap = () => {
    const a = [...pts.current.values()];
    const cur = zRef.current;
    if (a.length >= 2) return { d: Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y), s: cur.s, x: cur.x, y: cur.y, cx: (a[0].x + a[1].x) / 2, cy: (a[0].y + a[1].y) / 2 };
    return { d: 0, s: cur.s, x: cur.x, y: cur.y, cx: a[0]?.x ?? 0, cy: a[0]?.y ?? 0 };
  };
  const down = (e: RPointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    start.current = snap();
  };
  const move = (e: RPointerEvent) => {
    if (!pts.current.has(e.pointerId) || !start.current) return;
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const a = [...pts.current.values()];
    const st = start.current;
    const sc = k.stageScale || 1;
    if (a.length >= 2 && st.d > 0) {
      const s = Math.max(1, Math.min(5, (st.s * Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y)) / st.d));
      setZ({ s, x: st.x, y: st.y });
    } else if (a.length === 1 && zRef.current.s > 1) {
      setZ((v) => ({ ...v, x: st.x + (a[0].x - st.cx) / sc, y: st.y + (a[0].y - st.cy) / sc }));
    }
  };
  const up = (e: RPointerEvent) => {
    const st = start.current;
    const p = pts.current.get(e.pointerId);
    pts.current.delete(e.pointerId);
    if (pts.current.size === 0 && st && p) {
      const dx = p.x - st.cx, dy = p.y - st.cy;
      if (zRef.current.s <= 1.02 && Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy) * 1.5) onSwipe(dx < 0 ? 1 : -1);
      else if (Math.abs(dx) < 10 && Math.abs(dy) < 10) {
        if (Date.now() - lastTap.current < 320) { setZ((v) => (v.s > 1 ? { s: 1, x: 0, y: 0 } : { s: 2.5, x: 0, y: 0 })); lastTap.current = 0; }
        else lastTap.current = Date.now();
      }
      if (zRef.current.s <= 1.02) setZ({ s: 1, x: 0, y: 0 });
    }
    start.current = pts.current.size ? snap() : null;
  };
  return (
    <div className="zoom" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
      <img src={src} alt="" draggable={false} style={{ transform: `translate(${z.x}px, ${z.y}px) scale(${z.s})` }} />
      <div className="zoom-btns">
        <button onClick={() => setZ((v) => ({ ...v, s: Math.min(5, v.s + 0.75) }))} aria-label="+"><Icon name="plus" /></button>
        <button onClick={() => setZ((v) => (v.s - 0.75 <= 1 ? { s: 1, x: 0, y: 0 } : { ...v, s: v.s - 0.75 }))} aria-label="−"><Icon name="minus" /></button>
      </div>
    </div>
  );
}

export function Detail() {
  const k = useKiosk();
  const { t } = k;
  const p = (k.detail && k.byKey.get(k.detail)) || k.today[0];
  if (!p) return <div className="screen"><Bottom /></div>;
  const list = k.detailList.length ? k.detailList : k.today.map((x) => x.key);
  const idx = list.indexOf(p.key);
  const prev = idx > 0 ? list[idx - 1] : null;
  const next = idx >= 0 && idx < list.length - 1 ? list[idx + 1] : null;
  const nearby = k.today.filter((x) => x.key !== p.key && Math.abs(x.ts - p.ts) <= 240).sort((a, b) => a.ts - b.ts).slice(0, 8);
  const inCart = k.cart.some((i) => i.key === p.key);
  const prices = k.formats.map((f) => k.cfg.products[f].price);
  const from = prices.length ? Math.min(...prices) : 0;
  const nav = (dir: 1 | -1) => { const key = dir === 1 ? next : prev; if (key) k.openDetail(key); };
  return (
    <div className="screen detail">
      <div className="detail-body">
        <div className="detail-stage">
          <ZoomImage key={p.key} src={photoFull(p)} onSwipe={nav} />
          {prev && <button className="nav-btn prev" onClick={() => nav(-1)} aria-label={t('common.back')}><Icon name="left" /></button>}
          {next && <button className="nav-btn next" onClick={() => nav(1)} aria-label={t('detail.next')}><Icon name="right" /></button>}
          <span className="detail-hint"><Icon name="search" />{t('detail.zoom')}</span>
        </div>
        <aside className="detail-side">
          <div className="detail-id">
            <span className="chip">{t('detail.number', { n: p.number })}</span>
            <b>{k.time(p.ts)}</b>
          </div>
          <div className="detail-price">{t('detail.from', { x: k.money(from) })}</div>
          {inCart ? (
            <>
              <span className="chip chip-ok"><Icon name="check" />{t('detail.in_cart')}</span>
              <button className="btn btn-primary btn-xl full" onClick={() => k.go('cart')}><Icon name="cart" />{t('detail.to_cart')}</button>
            </>
          ) : (
            <button className="btn btn-primary btn-xl full" onClick={() => k.startBuy(p.key)}><Icon name="check" />{t('detail.choose')}</button>
          )}
          {nearby.length > 0 && (
            <>
              <h4 className="side-h">{t('detail.nearby')}</h4>
              <div className="nearby">
                {nearby.map((n) => (
                  <button key={n.key} onClick={() => k.openDetail(n.key)} className={k.cart.some((i) => i.key === n.key) ? 'in-cart' : ''}>
                    <img src={photoSrc(n)} alt="" loading="lazy" /><span>{k.time(n.ts)}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </aside>
      </div>
      <Bottom />
    </div>
  );
}
