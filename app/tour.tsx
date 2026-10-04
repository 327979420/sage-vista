"use client";
import {useCallback, useEffect, useRef, useState} from 'react';
import {useLocale} from './i18n/locale';
import {TOUR_COPY, TOUR_SEEN_KEY, TOUR_STEPS, tourSeen} from './tour-steps';

type Stage = 'closed' | 'welcome' | number | 'done';

function remember() {
 try { window.localStorage.setItem(TOUR_SEEN_KEY, '1'); } catch { /* storage may be disabled */ }
 try { document.cookie = `${TOUR_SEEN_KEY}=1; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`; } catch { /* cookies may be disabled */ }
}

// Client-only: nothing renders on the server, so crawlers and link previews
// never see the dialog. Replay with ?tour=1 (linked from the footer).
export default function Tour() {
 const {locale} = useLocale();
 const lang = locale === 'en' ? 'en' : 'zh';
 const [stage, setStage] = useState<Stage>('closed');
 const dialog = useRef<HTMLDivElement>(null);

 useEffect(() => {
  const replay = new URLSearchParams(location.search).get('tour') === '1';
  let stored: string | null = null;
  try { stored = window.localStorage.getItem(TOUR_SEEN_KEY); } catch { /* treat as unseen */ }
  // Decide after the first paint so server and client markup still match.
  const next: Stage = replay ? 0 : tourSeen(document.cookie, stored) ? 'closed' : 'welcome';
  const frame = requestAnimationFrame(() => setStage(next));
  return () => cancelAnimationFrame(frame);
 }, []);

 const close = useCallback((goToList: boolean) => {
  remember();
  setStage('closed');
  if (new URLSearchParams(location.search).has('tour')) history.replaceState(null, '', location.pathname + location.hash);
  if (goToList && location.pathname !== '/') location.href = '/';
 }, []);

 useEffect(() => {
  if (stage === 'closed') return;
  dialog.current?.querySelector<HTMLElement>('button')?.focus();
  const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') close(false); };
  window.addEventListener('keydown', onKey);
  return () => window.removeEventListener('keydown', onKey);
 }, [stage, close]);

 if (stage === 'closed') return null;
 const t = (key: keyof typeof TOUR_COPY) => TOUR_COPY[key][lang];
 const step = typeof stage === 'number' ? TOUR_STEPS[stage] : null;

 return <div className="svTourBackdrop">
  <div className="svTour" role="dialog" aria-modal="true" aria-labelledby="svTourTitle" ref={dialog}>
   {stage === 'welcome' && <div className="svTourWelcome">
    <h2 id="svTourTitle">{t('welcome')}</h2><p>{t('question')}</p>
    {/* Two equal choice tiles, so new and returning visitors decide at a glance. */}
    <div className="svTourChoices">
     <button type="button" className="svTourChoice isNew" onClick={() => setStage(0)}><span aria-hidden="true">👋</span><b>{t('no')}</b><small>{t('noSub')}</small></button>
     <button type="button" className="svTourChoice" onClick={() => close(true)}><span aria-hidden="true">🚀</span><b>{t('yes')}</b><small>{t('yesSub')}</small></button>
    </div>
    <button type="button" className="isQuiet svTourSkip" onClick={() => close(false)}>{t('skip')}</button>
   </div>}
   {step && typeof stage === 'number' && <div className="svTourStep">
    <small>{lang === 'en' ? `${t('step')} ${stage + 1} ${t('of')} ${TOUR_STEPS.length}` : `${t('step')} ${stage + 1} 步 ${t('of')} ${TOUR_STEPS.length}`}</small>
    {/* Static, pre-sized screenshot loaded only when the tour is open. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img src={`/tour/${lang}/${step.image}.webp`} alt="" width={1240} height={460}/>
    <h2 id="svTourTitle"><span aria-hidden="true">{step.icon}</span> {step.title[lang]}</h2>
    <p>{step.text[lang]}</p>
    <div className="svTourDots" aria-hidden="true">{TOUR_STEPS.map((s, i) => <i key={s.id} className={i === stage ? 'isOn' : ''}/>)}</div>
    <div className="svTourActions">
     <button type="button" className="isQuiet" onClick={() => close(false)}>{t('skipTour')}</button>
     <span>{stage > 0 && <button type="button" onClick={() => setStage(stage - 1)}>{t('back')}</button>}
      <button type="button" className="isPrimary" onClick={() => setStage(stage + 1 < TOUR_STEPS.length ? stage + 1 : 'done')}>{t('next')}</button></span>
    </div>
    {stage + 1 < TOUR_STEPS.length && <link rel="prefetch" href={`/tour/${lang}/${TOUR_STEPS[stage + 1].image}.webp`}/>}
   </div>}
   {stage === 'done' && <div className="svTourWelcome">
    <h2 id="svTourTitle">{t('doneTitle')}</h2><p>{t('doneText')}</p>
    <button type="button" className="isPrimary" onClick={() => close(true)}>{t('go')}</button>
   </div>}
  </div>
 </div>;
}
