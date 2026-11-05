import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { DEFAULT_CONFIG, LANGS } from '../config';
import { photoSrc } from '../data';
import { useKiosk } from '../store';
import { Bottom, Icon, Keypad, Logo, QR, Spinner } from '../ui';

export function Attract() {
  const k = useKiosk();
  const { cfg, t } = k;
  const { messages, slide_seconds, show_photos, headline, subline } = cfg.attract;
  const copy = messages[k.lang];
  const [slide, setSlide] = useState(0);
  const duration = slide_seconds * 1000;
  const shots = show_photos ? k.today.filter((p) => p.src).slice(0, 18) : [];
  const rows = k.portrait && shots.length >= 10 ? [shots.slice(0, 9), shots.slice(9)] : [shots];

  useEffect(() => {
    setSlide(0);
    const id = window.setInterval(() => setSlide((n) => n + 1), duration + 500);
    return () => window.clearInterval(id);
  }, [copy, headline, duration]);

  const defaultMessages = DEFAULT_CONFIG.attract.messages[k.lang];
  const useLegacyHeadline = k.lang === cfg.language && copy.length === defaultMessages.length && copy.every((text, i) => text === defaultMessages[i]);
  const customHeadline = useLegacyHeadline ? headline.trim() : '';
  const message = customHeadline && slide % copy.length === 0 ? customHeadline : copy[slide % copy.length];
  return (
    <div className="attract" onClick={() => k.start()}>
      <header className="attract-top"><Logo />{cfg.attract.show_count && k.today.length > 0 && <span className="chip">{t('attract.today', { n: k.today.length })}</span>}</header>
      {shots.length > 0 && <div className="attract-strip" aria-hidden="true">
        {rows.filter((row) => row.length).map((row, index) => {
          const repeated = Array.from({ length: Math.ceil(7 / row.length) }, () => row).flat();
          return <div className="attract-strip-track" key={index}>
            {[0, 1].map((segment) => <div key={segment}>{repeated.map((p, j) => <img key={j} src={photoSrc(p)} alt="" decoding="async" />)}</div>)}
          </div>;
        })}
      </div>}
      <div className="attract-center">
        <div className="attract-copy">
          <h1 className={message.length > 150 ? 'very-long' : message.length > 48 ? 'long' : undefined} key={`${k.lang}-${slide}`} style={{ '--slide-duration': `${duration + 500}ms` } as CSSProperties}>{message}</h1>
        </div>
        {subline && <p>{subline}</p>}
      </div>
      <footer className="attract-bottom">
        <button className="btn btn-primary btn-xxl attract-cta">{t('attract.tap')}</button>
        <div className="attract-langs" onClick={(e) => e.stopPropagation()}>
          {LANGS.filter((l) => cfg.languages.includes(l.id)).map((l) => (
            <button key={l.id} className={l.id === k.lang ? 'on' : ''} aria-label={l.name} onClick={() => k.start(l.id)}>{l.code}</button>
          ))}
        </div>
        {cfg.find.phone && cfg.attract.phone_qr && cfg.links.phone_search && (
          <div className="attract-qr" onClick={(e) => e.stopPropagation()}>
            <QR value={k.link(cfg.links.phone_search, [])} size="7rem" /><span>{t('attract.phone')}</span>
          </div>
        )}
      </footer>
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
  const video = useRef<HTMLVideoElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [count, setCount] = useState(3);
  const [state, setState] = useState<'camera' | 'count' | 'search' | 'none' | 'error'>('camera');

  useEffect(() => {
    let active = true;
    let stream: MediaStream | undefined;
    let countdown = 0;
    let timer = 0;
    let release: (() => void) | undefined;
    function stop() {
      window.clearInterval(countdown);
      window.clearTimeout(timer);
      release?.();
      stream?.getTracks().forEach((track) => track.stop());
    }
    async function run() {
      let image: string | null = null;
      try {
        if (k.hw.mode === 'host') {
          stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
          if (!active) { stop(); return; }
          const el = video.current!;
          el.srcObject = stream;
          await el.play();
          if (!active) return;
        }
        setState('count');
        setCount(3);
        await new Promise<void>((resolve) => {
          release = resolve;
          countdown = window.setInterval(() => setCount((n) => Math.max(1, n - 1)), 1000);
          timer = window.setTimeout(resolve, 3000);
        });
        if (!active) return;
        if (stream && video.current) {
          const canvas = document.createElement('canvas');
          canvas.width = 640;
          canvas.height = Math.round(640 * video.current.videoHeight / video.current.videoWidth);
          canvas.getContext('2d')?.drawImage(video.current, 0, 0, canvas.width, canvas.height);
          image = canvas.toDataURL('image/jpeg', 0.85);
        }
        stop();
        setState('search');
        const keys = await k.hw.faceSearch(image, k.today);
        if (!active) return;
        if (keys.length) k.find({ mode: 'face', faceKeys: keys }, true);
        else setState('none');
      } catch {
        if (active) setState('error');
      } finally { stop(); }
    }
    setState('camera');
    void run();
    return () => { active = false; stop(); };
  }, [attempt]); // Bildschirm oder neuer Suchversuch, nicht jedes eintreffende Foto.

  return (
    <div className="screen face">
      <div className="pad"><h1 className="title">{t('face.title')}</h1></div>
      <div className="face-body">
        <div className="face-cam">
          <video ref={video} muted playsInline hidden={k.hw.mode !== 'host' || !['camera', 'count'].includes(state)} />
          {(state === 'camera' || state === 'search') && <div className="face-search-label"><Spinner />{t('face.searching')}</div>}
          {state === 'count' && <div className="face-count">{count}<small>{t('face.hold')}</small></div>}
          {(state === 'none' || state === 'error') && <div className="face-none"><Icon name="search" /><p>{t(state === 'none' ? 'face.none' : 'scan.camera_error')}</p></div>}
        </div>
      </div>
      <Bottom>{(state === 'none' || state === 'error') && <button className="btn btn-primary" onClick={() => setAttempt((n) => n + 1)}>{t('face.again')}</button>}</Bottom>
    </div>
  );
}
