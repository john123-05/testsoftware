// Startbildschirm (laeuft, solange niemand davor steht), Begruessung und die Suchwege:
// Uhrzeit, Fotonummer, Gesicht.
import { useEffect, useMemo, useRef, useState } from 'react';
import { LANGS } from '../config';
import { photoFull, photoSrc, type Photo } from '../data';
import { useKiosk } from '../store';
import { Bottom, Icon, Keypad, Logo, QR, Spinner, type IconName } from '../ui';

export function Attract() {
  const k = useKiosk();
  const { cfg, t } = k;
  const slides = useMemo(() => k.today.slice(0, 8), [k.today]);
  const [i, setI] = useState(0);
  useEffect(() => {
    if (slides.length < 2) return;
    const id = window.setInterval(() => setI((x) => (x + 1) % slides.length), 6000);
    return () => window.clearInterval(id);
  }, [slides.length]);
  const strip = useMemo(() => k.today.slice(0, 14), [k.today]);
  return (
    <div className="attract" onClick={() => k.start()}>
      <div className="attract-bg">
        {slides.map((p, j) => <img key={p.key} src={photoFull(p)} alt="" className={j === i ? 'on' : ''} />)}
      </div>
      <div className="attract-shade" />
      <header className="attract-top">
        <Logo />
        {cfg.attract.show_count && k.today.length > 0 && (
          <span className="chip chip-glass"><span className="live-dot" />{t('attract.today', { n: k.today.length })}</span>
        )}
      </header>
      <div className="attract-center">
        <h1>{cfg.attract.headline || t('attract.headline')}</h1>
        <p>{cfg.attract.subline || t('attract.sub')}</p>
        <button className="btn btn-primary btn-xxl attract-cta"><Icon name="search" />{t('attract.tap')}</button>
      </div>
      {strip.length > 4 && k.tier !== 'low' && (
        <div className="attract-strip" aria-hidden="true">
          <div className="attract-strip-track">
            {[...strip, ...strip].map((p, j) => <img key={j} src={photoSrc(p)} alt="" />)}
          </div>
        </div>
      )}
      <footer className="attract-bottom">
        <div className="attract-langs" onClick={(e) => e.stopPropagation()}>
          {LANGS.filter((l) => cfg.languages.includes(l.id)).map((l) => (
            <button key={l.id} className={l.id === k.lang ? 'on' : ''} onClick={() => k.start(l.id)}>
              <b>{l.code}</b><small>{l.name}</small>
            </button>
          ))}
        </div>
        {cfg.find.phone && cfg.attract.phone_qr && (
          <div className="attract-qr" onClick={(e) => e.stopPropagation()}>
            <QR value={k.link(cfg.links.phone_search, [])} size="7.6rem" />
            <span><Icon name="phone" />{t('attract.phone')}</span>
          </div>
        )}
      </footer>
    </div>
  );
}

type Tile = { id: string; icon: IconName; title: string; sub: string; go: () => void };

export function Home() {
  const k = useKiosk();
  const { cfg, t } = k;
  const latest = k.today.slice(0, 12);
  const tiles: Tile[] = [];
  if (cfg.find.time) tiles.push({ id: 'time', icon: 'clock', title: t('home.time'), sub: t('home.time_sub'), go: () => k.go('time') });
  if (cfg.find.face && k.hwStatus.face) tiles.push({ id: 'face', icon: 'scan', title: t('home.face'), sub: t('home.face_sub'), go: () => k.go('face') });
  if (cfg.find.number) tiles.push({ id: 'number', icon: 'hash', title: t('home.number'), sub: t('home.number_sub'), go: () => k.go('number') });
  if (cfg.find.phone) tiles.push({ id: 'phone', icon: 'phone', title: t('home.phone'), sub: t('home.phone_sub'), go: () => k.setOverlay('handoff') });
  if (cfg.payments.voucher) tiles.push({ id: 'voucher', icon: 'ticket', title: t('home.voucher'), sub: t('home.voucher_sub'), go: () => k.go('voucher') });
  return (
    <div className="screen home">
      <div className="pad home-head">
        <div>
          <h1 className="title">{t('home.hello')}</h1>
          <p className="sub">{t('home.sub')}</p>
        </div>
        {k.voucher && (
          <span className="chip chip-accent"><Icon name="ticket" />
            {k.voucher.kind === 'day' ? t('home.pass_day') : t('home.pass_photos', { n: k.voucher.photos })}
          </span>
        )}
      </div>
      <div className={`home-grid n${tiles.length}`}>
        <button className="tile tile-hero" onClick={() => k.find({ mode: 'recent' })}>
          <div className="hero-photos">
            {latest.slice(0, 3).map((p, i) => <img key={p.key} src={photoSrc(p)} alt="" className={`hp hp${i}`} />)}
          </div>
          <div className="hero-body">
            <span className="hero-live"><span className="live-dot" />{t('home.live')}</span>
            <b>{t('home.just_rode')}</b>
            <small>{t('home.just_rode_sub', { n: cfg.find.just_rode_minutes })}</small>
          </div>
          <span className="hero-go"><Icon name="right" /></span>
        </button>
        {tiles.map((tile) => (
          <button key={tile.id} className="tile" onClick={tile.go}>
            <span className="tile-icon"><Icon name={tile.icon} /></span>
            <span className="tile-text"><b>{tile.title}</b><small>{tile.sub}</small></span>
            <Icon name="right" className="tile-chev" />
          </button>
        ))}
      </div>
      {latest.length > 0 && (
        <div className="home-latest">
          <h3>{t('home.latest')}</h3>
          <div className="strip">
            {latest.map((p) => (
              <button key={p.key} onClick={() => k.openDetail(p.key, k.today.map((x) => x.key))}>
                <img src={photoSrc(p)} alt="" loading="lazy" />
                <span>{k.time(p.ts)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function TimeScreen() {
  const k = useKiosk();
  const { t } = k;
  const hours = useMemo(() => {
    const m = new Map<number, Photo[]>();
    for (const p of k.today) {
      const h = new Date(p.ts * 1000).getHours();
      m.set(h, [...(m.get(h) ?? []), p]);
    }
    return [...m.entries()].sort((a, b) => Math.min(...a[1].map((p) => p.ts)) - Math.min(...b[1].map((p) => p.ts)));
  }, [k.today]);
  const [hour, setHour] = useState<number>(() => hours[hours.length - 1]?.[0] ?? new Date().getHours());
  const slots = useMemo(() => {
    const list = hours.find(([h]) => h === hour)?.[1] ?? [];
    return Array.from({ length: 12 }, (_, i) => {
      const inSlot = list.filter((p) => Math.floor(new Date(p.ts * 1000).getMinutes() / 5) === i);
      const d = new Date(); d.setHours(hour, i * 5, 0, 0);
      return { start: Math.floor(d.getTime() / 1000), photos: inSlot };
    });
  }, [hours, hour]);
  return (
    <div className="screen time">
      <div className="pad"><h1 className="title">{t('time.title')}</h1><p className="sub">{t('time.sub')}</p></div>
      <div className="hours">
        {hours.map(([h, list]) => (
          <button key={h} className={`hour${h === hour ? ' on' : ''}`} onClick={() => setHour(h)}>
            <b>{k.hour(h)}</b><small>{t('common.photos', { n: list.length })}</small>
          </button>
        ))}
      </div>
      <div className="slots">
        {slots.map((s) => (
          <button key={s.start} className="slot" disabled={!s.photos.length} onClick={() => k.find({ mode: 'time', time: s.start + 150 })}>
            <span className="slot-img">{s.photos[0] ? <img src={photoSrc(s.photos[0])} alt="" loading="lazy" /> : <Icon name="image" />}</span>
            <b>{k.time(s.start)}</b>
            <small>{s.photos.length ? t('common.photos', { n: s.photos.length }) : '–'}</small>
          </button>
        ))}
      </div>
      <Bottom />
    </div>
  );
}

export function NumberScreen() {
  const k = useKiosk();
  const [v, setV] = useState('');
  const [err, setErr] = useState(false);
  const press = (key: string) => {
    setErr(false);
    if (key === 'del') setV((x) => x.slice(0, -1));
    else if (key === 'clr') setV('');
    else setV((x) => (x + key).slice(0, 4));
  };
  const show = () => {
    const p = k.today.find((x) => x.number === v.padStart(4, '0'));
    if (p) k.openDetail(p.key, k.today.map((x) => x.key)); else setErr(true);
  };
  return (
    <div className="screen number">
      <div className="pad"><h1 className="title">{k.t('number.title')}</h1><p className="sub">{k.t('number.sub')}</p></div>
      <div className="number-body">
        <div className={`number-display${err ? ' shake' : ''}`}>
          {[0, 1, 2, 3].map((i) => <span key={i} className={v[i] ? 'f' : ''}>{v[i] ?? ''}</span>)}
        </div>
        <p className={`form-msg${err ? ' err' : ''}`}>{err ? k.t('number.none') : ' '}</p>
        <Keypad rows={[['1', '2', '3'], ['4', '5', '6'], ['7', '8', '9'], ['clr', '0', 'del']]} onKey={press} />
      </div>
      <Bottom>
        <button className="btn btn-primary btn-xl" disabled={v.length < 4} onClick={show}>{k.t('number.show')}<Icon name="right" /></button>
      </Bottom>
    </div>
  );
}

export function FaceScreen() {
  const k = useKiosk();
  const { t } = k;
  const [state, setState] = useState<'intro' | 'scan' | 'search' | 'none'>('intro');
  const [count, setCount] = useState(3);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [demo, setDemo] = useState(false);
  const video = useRef<HTMLVideoElement>(null);

  useEffect(() => () => stream?.getTracks().forEach((tr) => tr.stop()), [stream]);
  useEffect(() => { if (video.current && stream) { video.current.srcObject = stream; void video.current.play().catch(() => undefined); } }, [stream, state]);

  async function begin() {
    setState('scan'); setCount(3); setDemo(false);
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 1280, height: 720 }, audio: false });
      setStream(s);
    } catch { setDemo(true); }
  }
  useEffect(() => {
    if (state !== 'scan') return;
    if (count <= 0) { void capture(); return; }
    const id = window.setTimeout(() => setCount((c) => c - 1), 1000);
    return () => window.clearTimeout(id);
  }, [state, count]); // eslint-disable-line react-hooks/exhaustive-deps

  async function capture() {
    let image: string | null = null;
    if (video.current && stream) {
      const c = document.createElement('canvas');
      c.width = 640; c.height = 360;
      c.getContext('2d')?.drawImage(video.current, 0, 0, 640, 360);
      image = c.toDataURL('image/jpeg', 0.85);
    }
    stream?.getTracks().forEach((tr) => tr.stop());
    setStream(null);
    setState('search');
    const keys = await k.hw.faceSearch(image, k.today);
    image = null; // Bild sofort verwerfen
    if (keys.length) k.find({ mode: 'face', faceKeys: keys }, true); else setState('none');
  }

  return (
    <div className="screen face">
      <div className="pad"><h1 className="title">{t('face.title')}</h1><p className="sub">{t('face.sub')}</p></div>
      <div className="face-body">
        <div className={`face-cam state-${state}`}>
          {stream && <video ref={video} muted playsInline />}
          {!stream && (state === 'scan' || demo) && state !== 'search' && <div className="face-demo"><Icon name="scan" /><span>{t('face.demo')}</span></div>}
          {state === 'intro' && <div className="face-intro"><Icon name="scan" /></div>}
          {(state === 'scan' || state === 'intro') && <div className="face-oval" />}
          {state === 'scan' && <div className="face-count">{count > 0 ? count : <Icon name="camera" />}<small>{t('face.hold')}</small></div>}
          {state === 'search' && (
            <div className="face-search">
              <div className="face-grid">{k.today.slice(0, 24).map((p) => <img key={p.key} src={photoSrc(p)} alt="" />)}</div>
              <div className="face-sweep" />
              <div className="face-search-label"><Spinner />{t('face.searching')}</div>
            </div>
          )}
          {state === 'none' && <div className="face-none"><Icon name="search" /><p>{t('face.none')}</p></div>}
        </div>
        <p className="face-privacy"><Icon name="lock" />{t('face.privacy')}</p>
      </div>
      <Bottom>
        {state === 'intro' && <button className="btn btn-primary btn-xl" onClick={() => void begin()}><Icon name="camera" />{t('face.start')}</button>}
        {state === 'none' && (
          <>
            <button className="btn btn-ghost btn-xl" onClick={() => k.go('time', { replace: true })}><Icon name="clock" />{t('face.by_time')}</button>
            <button className="btn btn-primary btn-xl" onClick={() => void begin()}>{t('face.again')}</button>
          </>
        )}
      </Bottom>
    </div>
  );
}
