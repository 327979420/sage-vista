'use client';
import {useEffect} from 'react';
import {useLocale} from './i18n/locale';
import {INTRO_HREF,markSeen} from './first-visit';

// One line for a first-timer who lands on the Multi-factor list: what the list is and is not.
export default function FirstVisitBanner() {
 const {locale}=useLocale(), en=locale==='en';
 useEffect(()=>{markSeen()},[]);
 return <aside className="fvBanner">
  <p><b>{en?'Every day about 1,500 US stocks are scored on monthly, weekly and daily charts.':'每天给约 1,500 只美股按月线、周线、日线打分。'}</b>{en?' The score says which to research first. It is not a buy list or a win rate.':'分数决定先研究哪几只，不是买入清单，也不是胜率。'}</p>
  <a href={INTRO_HREF}>{en?'What is SV? →':'SV 是什么？→'}</a>
 </aside>;
}
