'use client';
import {useEffect, useState, type KeyboardEvent} from 'react';
import {useLocale} from '../i18n/locale';
import {sharedJson} from '../json-cache';
import {INDEX_URL, W3_URLS, stockHref, suggest, tags, validIndex, withLive3W, type StockIndex} from './lookup';

// The daily index, with its 3W part refreshed from the files the 3W page reads (see withLive3W).
export const loadIndex = () => Promise.all([sharedJson<unknown>(INDEX_URL), sharedJson<unknown>(W3_URLS.signals), sharedJson<unknown>(W3_URLS.today), sharedJson<unknown>(W3_URLS.record)])
 .then(([index, signals, today, record]) => (validIndex(index) ? withLive3W(index, {signals, today, record}) : null));
export function useIndex(enabled = true) {
 const [state, setState] = useState<{index: StockIndex | null; ready: boolean}>({index: null, ready: false});
 useEffect(() => {
  if (!enabled) return;
  let on = true;
  loadIndex().then(index => { if (on) setState({index, ready: true}); });
  return () => { on = false; };
 }, [enabled]);
 return state;
}

// Ticker search with type-ahead for the /stock pages (one per page, so its ids are fixed).
export function StockSearch({initial = ''}: {initial?: string}) {
 const {locale} = useLocale(), en = locale === 'en', id = 'sl-search';
 const {index} = useIndex();
 const [value, setValue] = useState(initial), [open, setOpen] = useState(false), [sel, setSel] = useState(-1);
 const items = index && open ? suggest(value, index) : [];
 const go = (symbol: string) => { if (symbol.trim()) location.assign(stockHref(symbol.trim())); };
 const submit = () => {
  const typed = value.trim().toUpperCase();
  go(sel >= 0 && items[sel] ? items[sel] : items.length && !(index && index.stocks[typed]) && !/[.\d]/.test(typed) ? items[0] : value);
 };
 const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
  if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && items.length) { e.preventDefault(); setSel((sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length); }
  else if (e.key === 'Enter') { e.preventDefault(); submit(); }
  else if (e.key === 'Escape') setOpen(false);
 };
 return <form className="slSearch" role="search" onSubmit={e => { e.preventDefault(); submit(); }}>
  <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
  <input type="search" value={value} autoComplete="off" spellCheck={false} enterKeyHint="search"
   placeholder={en ? 'Ticker, e.g. NVDA' : '股票代码，如 NVDA'}
   aria-label={en ? 'Look up a stock ticker' : '查股票代码'} role="combobox" aria-expanded={items.length > 0} aria-controls={`${id}-list`} aria-autocomplete="list"
   aria-activedescendant={sel >= 0 && items[sel] ? `${id}-${sel}` : undefined}
   onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 120)}
   onChange={e => { setValue(e.target.value); setSel(-1); setOpen(true); }} onKeyDown={onKey}/>
  {items.length > 0 && <ul id={`${id}-list`} role="listbox" className="slSugg">{items.map((s, i) => <li key={s} id={`${id}-${i}`} role="option" aria-selected={i === sel}
   onMouseDown={e => { e.preventDefault(); go(s); }}><b>{s}</b><span>{tags(index!.stocks[s], en).join(' · ') || (en ? 'tracked' : '在跟')}</span></li>)}</ul>}
 </form>;
}

