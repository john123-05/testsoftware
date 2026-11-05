// Kaufen: Format waehlen (eine Entscheidung pro Bildschirm), Warenkorb mit ehrlicher Summe, Zahlart.
import { photoFull, photoSrc } from '../data';
import { useKiosk } from '../store';
import { Bottom, Icon, QR, type IconName } from '../ui';
import { printHomeLink, type Format, type PayMethod } from '../config';

const FORMAT_ICON: Record<Format, IconName> = { print: 'printer', digital: 'phone', combo: 'combo' };

export function Products() {
  const k = useKiosk();
  const { t, cfg } = k;
  const p = k.buying ? k.byKey.get(k.buying) : null;
  const ship = printHomeLink(cfg.links.print_home, p?.code);
  const separate = cfg.products.print.price + cfg.products.digital.price;
  const comboSave = cfg.products.print.enabled && cfg.products.digital.enabled ? separate - cfg.products.combo.price : 0;
  const dayPass = k.voucher?.kind === 'day';
  return (
    <div className="screen products">
      <div className="pad"><h1 className="title">{t('products.title')}</h1></div>
      <div className="prod-wrap">
        {p && <div className="prod-photo"><img src={photoFull(p)} alt="" /><span className="chip">{t('detail.number', { n: p.number })} · {k.time(p.ts)}</span></div>}
        <div className="prod-list">
          {k.formats.map((f) => {
            const best = f === 'combo' && comboSave > 0;
            const included = dayPass && f === 'digital';
            return (
              <button key={f} className="prod" onClick={() => k.choose(f)}>
                <span className="prod-icon"><Icon name={FORMAT_ICON[f]} /></span>
                <span className="prod-text">
                  <b>{t(`products.${f}`)}</b>
                  {best && <em>{t('products.save', { x: k.money(comboSave) })}</em>}
                  {included && <em>{t('products.included')}</em>}
                </span>
                <span className="prod-price">{included ? k.money(0) : k.money(cfg.products[f].price)}</span>
              </button>
            );
          })}
          {ship && <button className="prod" onClick={() => k.go('print_home')}>
            <span className="prod-icon"><Icon name="delivery" /></span>
            <span className="prod-text"><b>{t('ship.title')}</b></span>
          </button>}
        </div>
      </div>
      <Bottom />
    </div>
  );
}

export function PrintHome() {
  const k = useKiosk();
  const photo = k.buying ? k.byKey.get(k.buying) : null;
  const url = printHomeLink(k.cfg.links.print_home, photo?.code);
  return <div className="screen print-home">
    <div className="handoff-body">
      {url && <QR value={url} size="22rem" />}
      <div><h1 className="title">{k.t('ship.title')}</h1><p className="sub">{k.t(url ? 'ship.instructions' : 'ship.unavailable')}</p></div>
    </div>
    <Bottom />
  </div>;
}

export function Cart() {
  const k = useKiosk();
  const { t, pricing } = k;
  const add = () => k.backTo('gallery');
  return (
    <div className="screen cart">
      <div className="pad"><h1 className="title">{t('cart.title')}</h1></div>
      <div className="cart-wrap">
        <div className="cart-items">
          {k.cart.map((it, i) => {
            const p = k.byKey.get(it.key);
            return (
              <div className="cart-item" key={`${it.key}-${i}`}>
                {p && <img src={photoSrc(p)} alt="" />}
                <div className="ci-text">
                  <b><Icon name={FORMAT_ICON[it.format]} />{t(`products.${it.format}`)}</b>
                  {p && <small>{t('detail.number', { n: p.number })} · {k.time(p.ts)}</small>}
                </div>
                <span className="ci-price">{k.money(pricing.unit[it.format])}</span>
                <button className="ci-remove" onClick={() => k.remove(i)} aria-label={t('cart.remove')}><Icon name="trash" /></button>
              </div>
            );
          })}
          {!k.cart.length && <p className="empty">{t('cart.empty')}</p>}
          <button className="cart-add" onClick={add}><Icon name="plus" />{t('cart.add')}</button>
          {pricing.hint && (
            <button className="cart-hint" onClick={add}>
              <Icon name="sparkle" />
              <span>{t('cart.hint', { n: pricing.hint.more, m: pricing.hint.photos, x: k.money(pricing.hint.price) })}. <em>{t('cart.hint_save', { x: k.money(pricing.hint.save) })}</em></span>
            </button>
          )}
        </div>
        <div className="cart-sum">
          <div className="sum-row"><span>{t('cart.subtotal')}</span><b>{k.money(pricing.subtotal)}</b></div>
          {pricing.packageSaving > 0 && <div className="sum-row save"><span>{t('cart.package')}</span><b>−{k.money(pricing.packageSaving)}</b></div>}
          {pricing.passDiscount > 0 && <div className="sum-row save"><span>{t('cart.pass')}</span><b>−{k.money(pricing.passDiscount)}</b></div>}
          <div className="sum-total"><span>{t('cart.total')}</span><b>{k.money(pricing.total)}</b></div>
          {k.credit > 0 && pricing.total > 0 && <p className="sum-note"><Icon name="coins" />{t('cart.credit', { x: k.money(k.credit) })}</p>}
          <button className="btn btn-primary btn-xl full" disabled={!k.cart.length} onClick={k.pay}>
            {pricing.total > 0 ? t('cart.pay', { x: k.money(pricing.total) }) : t('cart.free')}<Icon name="right" />
          </button>
        </div>
      </div>
      <Bottom />
    </div>
  );
}

const METHOD_ICON: Record<PayMethod, IconName> = { card: 'card', cash: 'coins', phone: 'phone', voucher: 'ticket' };

export function Method() {
  const k = useKiosk();
  const { t } = k;
  return (
    <div className="screen method-screen">
      <div className="pad"><h1 className="title">{t('method.title')}</h1><p className="sub">{t('method.total', { x: k.money(k.pricing.total) })}</p></div>
      <div className={`method-grid n${k.methods.length}`}>
        {k.methods.map((m) => (
          <button key={m.id} className="method" disabled={m.disabled} onClick={() => k.go(m.screen)}>
            <span className="method-icon"><Icon name={METHOD_ICON[m.id]} /></span>
            <b>{t(`method.${m.id}`)}</b>
            {m.note && <em>{m.note}</em>}
          </button>
        ))}
      </div>
      <Bottom />
    </div>
  );
}
