"use client";
import {useCallback, useEffect, useRef, useState} from 'react';
import {useLocale} from './i18n/locale';
import {trackEvent} from './analytics';
import {TOUR_COPY, TOUR_SEEN_KEY, TOUR_STEPS, tourSeen} from './tour-steps';

function remember() {
 try { window.localStorage.setItem(TOUR_SEEN_KEY, '1'); } catch { /* storage may be disabled */ }
 try { document.cookie = `${TOUR_SEEN_KEY}=1; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`; } catch { /* cookies may be disabled */ }
}

// Top-bar "New here?" button with a small panel of four pages. New visitors see a quiet
// pulse on the button instead of a full-screen welcome; /?tour=1 opens the panel.
export default function StartHere() {
 const {locale} = useLocale();
 const lang = locale === 'en' ? 'en' : 'zh';
 const [open, setOpen] = useState(false);
 const [fresh, setFresh] = useState(false);
 const box = useRef<HTMLDivElement>(null);

 useEffect(() => {
  const replay = new URLSearchParams(location.search).get('tour') === '1';
  let stored: string | null = null;
  try { stored = window.localStorage.getItem(TOUR_SEEN_KEY); } catch { /* treat as unseen */ }
  // Decide after the first paint so server and client markup still match.
  const frame = requestAnimationFrame(() => { setFresh(!tourSeen(document.cookie, stored)); if (replay) setOpen(true); });
  return () => cancelAnimationFrame(frame);
 }, []);

 const close = useCallback(() => {
  remember();
  setFresh(false);
  setOpen(false);
  if (new URLSearchParams(location.search).has('tour')) history.replaceState(null, '', location.pathname + location.hash);
 }, []);

 useEffect(() => {
  if (!open) return;
  trackEvent('start_here_opened');
  const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') close(); };
  const onDown = (event: MouseEvent) => { if (box.current && !box.current.contains(event.target as Node)) close(); };
  window.addEventListener('keydown', onKey);
  window.addEventListener('mousedown', onDown);
  return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('mousedown', onDown); };
 }, [open, close]);

 const t = (key: keyof typeof TOUR_COPY) => TOUR_COPY[key][lang];
 return <div className="svStart" ref={box}>
  <button type="button" className="svStartButton" aria-expanded={open} aria-controls="svStartPanel" onClick={() => open ? close() : setOpen(true)}>
   {t('button')}{fresh && !open && <em aria-hidden="true"/>}
  </button>
  {open && <div className="svStartPanel" id="svStartPanel" role="dialog" aria-label={t('title')}>
   <b>{t('title')}</b>
   <ol>{TOUR_STEPS.map((step, i) => <li key={step.id}>
    <a href={step.href} onClick={() => { trackEvent('start_here_step', {step: step.id, number: i + 1}); remember(); }}>
     <span>{String(i + 1).padStart(2, '0')}</span><strong>{step.title[lang]}</strong><small>{step.text[lang]}</small>
    </a>
   </li>)}</ol>
   <button type="button" className="svStartClose" onClick={close}>{t('close')}</button>
  </div>}
 </div>;
}
