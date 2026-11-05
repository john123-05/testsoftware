// Preise: Einzelpreis je Format, Pakete (guenstigste Kombination), Tagespass / Gratis-Fotos.
// Ehrlich gerechnet: der Gast sieht immer die Summe und was ein Paket wirklich spart.
import { FORMATS, type Format, type KioskConfig } from './config';
import type { Voucher } from './hardware';

export type Item = { key: string; format: Format };

export type Pricing = {
  subtotal: number;
  packageSaving: number;
  passDiscount: number;
  total: number;
  unit: Record<Format, number>;
  /** "Noch 1 dazu: 3 Fotos fuer 12 €" - nur wenn es wirklich spart. */
  hint: { format: Format; more: number; photos: number; price: number; save: number } | null;
};

/** Guenstigste Kombination aus Einzelpreis und Paketen fuer n Fotos. */
export function cheapest(n: number, single: number, packs: { photos: number; price: number }[]): number {
  const cost = [0];
  for (let i = 1; i <= n; i++) {
    let best = cost[i - 1] + single;
    for (const p of packs) if (p.photos <= i) best = Math.min(best, cost[i - p.photos] + p.price);
    cost.push(best);
  }
  return cost[n];
}

export function priceCart(items: Item[], cfg: KioskConfig, voucher: Voucher | null): Pricing {
  const unit = { print: cfg.products.print.price, digital: cfg.products.digital.price, combo: cfg.products.combo.price };
  let subtotal = 0;
  let packaged = 0;
  let hint: Pricing['hint'] = null;
  const count = (f: Format) => items.filter((i) => i.format === f).length;
  const packs = (f: Format) => cfg.packages.filter((p) => p.format === f);

  for (const f of FORMATS) {
    const n = count(f);
    const cost = cheapest(n, unit[f], packs(f));
    subtotal += n * unit[f];
    packaged += cost;
    if (n === 0) continue;
    for (const p of packs(f)) {
      const more = p.photos - n;
      if (more < 1 || more > 2) continue;
      const price = cheapest(p.photos, unit[f], packs(f));
      const save = p.photos * unit[f] - price;
      if (save > 0 && (!hint || save > hint.save)) hint = { format: f, more, photos: p.photos, price, save };
    }
  }

  // Pass: Tagespass = digitale Fotos gratis (bei Druck+digital zahlt man nur den Druck);
  // Foto-Guthaben = so viele digitale Fotos gratis.
  let pass = 0;
  if (voucher) {
    const digital = count('digital');
    const combo = count('combo');
    const digitalPart = Math.max(0, unit.combo - unit.print);
    if (voucher.kind === 'day') {
      pass = cheapest(digital, unit.digital, packs('digital')) + combo * digitalPart;
    } else {
      let left = voucher.photos;
      const d = Math.min(left, digital);
      pass += d * unit.digital;
      left -= d;
      pass += Math.min(left, combo) * digitalPart;
    }
  }
  pass = Math.min(pass, packaged);
  return { subtotal, packageSaving: subtotal - packaged, passDiscount: pass, total: packaged - pass, unit, hint };
}
