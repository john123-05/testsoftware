// Leistungsstufe des PCs: wie viel Animation sich der Rechner leisten kann.
// Gemessen werden Bilder pro Sekunde, Prozessorkerne und Arbeitsspeicher. Faellt die Bildrate im Betrieb
// dauerhaft ab (z. B. Grafiktreiber, Hitze), schaltet die App eine Stufe zurueck.
//   high: Ken-Burns-Hintergrund, Unschaerfe, Konfetti, weiche Uebergaenge
//   mid:  kurze Uebergaenge, keine Unschaerfe
//   low:  keine Animationen - alles erscheint sofort
import { useEffect, useState } from 'react';
import type { Tier } from './config';

function fps(ms: number): Promise<number> {
  return new Promise((resolve) => {
    let frames = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      frames++;
      if (t - t0 < ms) requestAnimationFrame(tick);
      else resolve((frames * 1000) / (t - t0));
    };
    requestAnimationFrame(tick);
  });
}

export async function detectTier(): Promise<Tier> {
  const cores = navigator.hardwareConcurrency || 2;
  const mem = (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 4;
  const f = await fps(1000);
  if (f < 38 || cores <= 2 || mem < 2) return 'low';
  if (f < 54 || cores <= 4 || mem <= 4) return 'mid';
  return 'high';
}

export function useTier(setting: 'auto' | Tier): Tier {
  const [tier, setTier] = useState<Tier>(setting === 'auto' ? 'mid' : setting);
  useEffect(() => {
    if (setting !== 'auto') { setTier(setting); return; }
    let alive = true;
    void detectTier().then((t) => { if (alive) setTier(t); });
    let slow = 0;
    const id = window.setInterval(async () => {
      if (document.hidden) return;
      const f = await fps(700);
      if (f < 30) { slow++; if (slow >= 2) { setTier((t) => (t === 'high' ? 'mid' : 'low')); slow = 0; } } else slow = 0;
    }, 9000);
    return () => { alive = false; window.clearInterval(id); };
  }, [setting]);
  useEffect(() => {
    document.documentElement.dataset.tier = tier;
    document.documentElement.style.setProperty('--dur', tier === 'high' ? '380ms' : tier === 'mid' ? '220ms' : '1ms');
  }, [tier]);
  return tier;
}
