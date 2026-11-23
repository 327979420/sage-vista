'use client';
import {useEffect} from 'react';
import {useLocale} from './i18n/locale';
import {INTRO_HREF,markSeen} from './first-visit';

// One line for a first-timer who lands on the Multi-factor list: what the list is and is not.
export default function FirstVisitBanner() {
 const {locale}=useLocale(), en=locale==='en';
 useEffect(()=>{markSeen()},[]);
 return <aside className="fvBanner">
  <p><b>{en?'About 1,500 US stocks scored daily on monthly, weekly and daily charts.':'每天给约 1,500 只美股按月、周、日线打分。'}</b>{en?' A research shortlist, not a buy list.':'先研究哪几只，不是买入清单。'}</p>
  <a href={INTRO_HREF}>{en?'What is SV? →':'SV 是什么？→'}</a>
 </aside>;
}
