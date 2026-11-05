import { useEffect, useRef, useState, type FormEvent } from 'react';
import jsQR from 'jsqr';
import type { PickupCode } from '../hardware';
import { useKiosk } from '../store';
import { Bottom, Icon, Spinner } from '../ui';

export function Scan() {
  const k = useKiosk();
  const current = useRef(k);
  current.current = k;
  const video = useRef<HTMLVideoElement>(null);
  const inFlight = useRef(false);
  const previous = useRef('');
  const [value, setValue] = useState('');
  const [result, setResult] = useState('');
  const [camera, setCamera] = useState<'off' | 'on' | 'error'>('off');
  const [checking, setChecking] = useState(false);

  async function read(raw: string) {
    const text = raw.trim();
    const kiosk = current.current;
    if (!text || text.length > 512 || inFlight.current || kiosk.overlay) return;
    inFlight.current = true;
    setChecking(true);
    setResult('');
    setValue('');
    kiosk.setBusy(true);
    let printing = false;
    try {
      const pickup = /^LPPICK:(order|grant):([a-f0-9-]{36}):([a-f0-9]{64})$/i.exec(text);
      if (pickup) {
        if (kiosk.hwStatus.printer !== 'ready') { setResult('printer'); return; }
        const code: PickupCode = { kind: pickup[1].toLowerCase() as PickupCode['kind'], id: pickup[2].toLowerCase(), token: pickup[3].toLowerCase() };
        const check = await kiosk.hw.pickup(code);
        if (check.status !== 'ready') { setResult(check.status); return; }
        const byCode = new Map(current.current.today.map((photo) => [photo.code, photo]));
        const photos = check.codes.map((c) => byCode.get(c)).filter((p) => p !== undefined);
        if (!photos.length || photos.length !== check.codes.length || (kiosk.hw.mode === 'host' && photos.some((p) => !p.file))) {
          setResult('missing'); return;
        }
        const claimed = await kiosk.hw.pickup(code, photos);
        if (claimed.status !== 'claimed') { setResult(claimed.status); return; }
        printing = true;
        kiosk.finishPickup(photos);
        return;
      }

      let photoCode = text;
      if (/^https?:\/\//i.test(text)) {
        const url = new URL(text);
        if (!url.pathname.replace(/\/$/, '').endsWith('/claim')) { setResult('invalid'); return; }
        photoCode = url.searchParams.get('code') ?? '';
      }
      if (/^\d{16}$/.test(photoCode)) {
        const photo = kiosk.today.find((p) => p.code === photoCode);
        if (photo) kiosk.openDetail(photo.key, [photo.key], true);
        else setResult('missing');
        return;
      }

      if (/^[a-z0-9]{8}$/i.test(text) && kiosk.cfg.payments.voucher) {
        const voucher = await kiosk.hw.voucherCheck(text.toUpperCase(), kiosk.cfg.vouchers.secret);
        if (voucher) {
          kiosk.setVoucher(voucher);
          if (kiosk.cart.length) kiosk.go('cart', { replace: true });
          else kiosk.back();
        } else setResult('voucher');
      } else setResult('invalid');
    } catch { setResult('invalid'); }
    finally {
      inFlight.current = false;
      setChecking(false);
      if (!printing) kiosk.setBusy(false);
    }
  }
  const onRead = useRef(read);
  onRead.current = read;

  useEffect(() => {
    if (k.hw.mode === 'sim' && !new URLSearchParams(location.search).has('camera')) return;
    let active = true;
    let stream: MediaStream | undefined;
    let timer = 0;
    const el = video.current!;
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d', { willReadFrequently: true });
    async function start() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'user' }, width: { ideal: 960 } }, audio: false });
        if (!active) { stream.getTracks().forEach((track) => track.stop()); return; }
        el.srcObject = stream;
        await el.play();
        if (!active) return;
        setCamera('on');
        timer = window.setInterval(() => {
          if (!context || !el.videoWidth || inFlight.current || current.current.overlay) return;
          canvas.width = Math.min(el.videoWidth, 800);
          canvas.height = Math.round(el.videoHeight * canvas.width / el.videoWidth);
          context.drawImage(el, 0, 0, canvas.width, canvas.height);
          const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
          const code = jsQR(pixels.data, pixels.width, pixels.height, { inversionAttempts: 'attemptBoth' })?.data ?? '';
          if (code && code !== previous.current) void onRead.current(code);
          previous.current = code;
        }, k.tier === 'low' ? 450 : 220);
      } catch {
        stream?.getTracks().forEach((track) => track.stop());
        if (active) setCamera('error');
      }
    }
    void start();
    return () => {
      active = false;
      window.clearInterval(timer);
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [k.hw.mode, k.tier]);

  useEffect(() => {
    let buffer = '';
    let lastKey = 0;
    function keydown(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement || current.current.overlay ||
          event.metaKey || event.altKey || event.ctrlKey) return;
      const now = performance.now();
      if (now - lastKey > 500) buffer = '';
      lastKey = now;
      if (event.key === 'Enter' && buffer) {
        event.preventDefault();
        event.stopPropagation();
        void onRead.current(buffer);
        buffer = '';
      } else if (event.key.length === 1 && buffer.length < 512) buffer += event.key;
    }
    window.addEventListener('keydown', keydown, true);
    return () => window.removeEventListener('keydown', keydown, true);
  }, []);

  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); void read(value); };
  return (
    <div className="screen scan-screen">
      <div className="pad"><h1 className="title">{k.t('scan.title')}</h1></div>
      <div className="scan-body">
        <div className="scan-view">
          <video ref={video} muted playsInline hidden={camera !== 'on'} />
          {camera !== 'on' && <Icon name="scan" />}
        </div>
        <div>
          <p className="sub">{k.t('scan.instructions')}</p>
          {camera === 'error' && <p className="sub">{k.t('scan.camera_error')}</p>}
          <form className="scan-input" onSubmit={submit}>
            <input autoFocus value={value} maxLength={512} onChange={(event) => setValue(event.target.value)}
              type="text" autoComplete="off" spellCheck={false} aria-label={k.t('scan.input')} placeholder={k.t('scan.input')} />
            <button className="btn btn-primary" type="submit" disabled={!value.trim() || checking}>{k.t('scan.submit')}</button>
          </form>
          <p className="form-msg" role="status">
            {checking ? <><Spinner /> {k.t('scan.checking')}</> : result ? k.t(result === 'voucher' ? 'voucher.invalid' : `scan.${result}`) : null}
          </p>
        </div>
      </div>
      <Bottom />
    </div>
  );
}
