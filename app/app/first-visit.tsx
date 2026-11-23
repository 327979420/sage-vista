'use client';
import {useEffect,useState,type CSSProperties} from 'react';
import {useLocale} from '../i18n/locale';
import {trackEvent} from '../analytics';
import {markSeen,RULE_LOCKED} from '../first-visit';
import type {SignalRow} from './signal-rows';
import SignalChart from './signal-chart';

// First-visit hero on Today. A first-timer gets, on one screen: a concrete question, what SV is in
// one sentence, three live numbers and one next step (NN/g homepage principles), plus a replay of
// this week's real scan. Every number and stock comes from the published data.
const ease = (p:number) => 1-Math.pow(1-p,3);
function useCountUp(target:number|null) {
 const [value,setValue]=useState<number|null>(null);
 useEffect(()=>{
  if(target===null)return;
  const still=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const start=performance.now();let frame=0;
  const step=(now:number)=>{const p=still?1:Math.min(1,(now-start)/900);setValue(Math.round(target*ease(p)));if(p<1)frame=requestAnimationFrame(step)};
  frame=requestAnimationFrame(step);
  return()=>cancelAnimationFrame(frame);
 },[target]);
 return value;
}

const pct = (v:number|null) => v===null?'—':`${(v*100).toFixed(1)}%`;
function checks(r:SignalRow,en:boolean):[string,boolean|null,string][] {
 return [
  [en?'Shape':'形态',r.shapeTotal?r.shapePassed===r.shapeTotal:null,`${r.shapePassed}/${r.shapeTotal}`],
  [en?'Reward/risk':'盈亏比',r.rrOk,r.rr===null?'—':`${r.rr.toFixed(2)}${r.rrOk===false?(en?' (needs 1.5)':'（要 1.5）'):''}`],
  [en?'Market':'大盘',r.gateOk,`${pct(r.breadth)}${r.gateOk===false?(en?' (needs 50%)':'（要过 50%）'):''}`],
 ];
}

// The deck: this week's signals, then one earlier example of each other reason (market light, monthly veto).
function deckOf(rows:SignalRow[]) {
 const charted=rows.filter(r=>r.chart&&r.chart.bars.length>1);
 const week=charted.map(r=>r.week).sort().at(-1);
 const latest=charted.filter(r=>r.week===week), earlier=charted.filter(r=>r.week!==week).sort((a,b)=>b.week.localeCompare(a.week));
 const extra=[earlier.find(r=>r.gateOk===false&&r.rrOk!==false&&!r.veto),earlier.find(r=>r.veto),earlier.find(r=>r.status!=='skipped')].filter((r):r is SignalRow=>!!r);
 return [...latest,...extra];
}
function verdictLine(r:SignalRow,en:boolean) {
 if(r.status==='open')return en?'Order filled, position open':'已成交，持仓中';
 if(r.status==='closed')return en?'Trade closed, counted':'已平仓，计入成绩';
 if(r.status==='waiting')return en?'Limit order placed':'限价单已挂出';
 // The checks above already give the numbers; this line only says what happened.
 return r.ruleOk?(en?'Skipped: stopped by the market light':'不做：被市场灯拦下'):(en?'Skipped: failed the rule':'不做：规则不过');
}
const SLIDE_MS=7500;

// A self-playing reel of real signals (story-style progress bars): nothing to click, but it pauses on
// hover or focus and has a pause button (WCAG 2.2.2); with reduced motion it stays on one chart.
function Film({rows,en}:{rows:SignalRow[]|null;en:boolean}) {
 const deck=rows?deckOf(rows):[];
 const [idx,setIdx]=useState(0);
 const [held,setHeld]=useState(false);
 const [paused,setPaused]=useState(false);
 const [still,setStill]=useState(false);
 useEffect(()=>{const id=requestAnimationFrame(()=>setStill(!!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches));return()=>cancelAnimationFrame(id)},[]);
 const stopped=paused||held||still;
 useEffect(()=>{if(stopped||deck.length<2)return;const id=setTimeout(()=>setIdx(v=>(v+1)%deck.length),SLIDE_MS);return()=>clearTimeout(id)},[idx,stopped,deck.length]);
 const r=deck[idx%Math.max(1,deck.length)];
 return <div className="fvFilm" data-stopped={stopped||undefined} style={{'--slide':`${SLIDE_MS}ms`} as CSSProperties}
  onMouseEnter={()=>setHeld(true)} onMouseLeave={()=>setHeld(false)} onFocus={()=>setHeld(true)} onBlur={()=>setHeld(false)}>
  <div className="fvStory" aria-hidden="true">{deck.map((d,i)=><i key={d.id} data-state={i<idx?'done':i===idx?'now':undefined}>{i===idx&&<b key={idx}/>}</i>)}</div>
  {r?<div className="fvSlide" key={r.id}>
   <header><span className="fvSym">{r.symbol}<small>{en?`week of ${r.week.slice(5)}`:`${r.week.slice(5)} 周`}</small></span>
    <button type="button" onClick={()=>setPaused(v=>!v)} aria-label={paused?(en?'Play':'播放'):(en?'Pause':'暂停')}>{paused?'▶':'❚❚'}</button></header>
   <SignalChart r={r} en={en}/>
   <div className="fvChecks">{checks(r,en).map(([label,ok,value],j)=><span key={label} data-ok={ok===null?undefined:String(ok)} style={{animationDelay:`${2.7+j*.22}s`}}><i>{ok===null?'·':ok?'✓':'✕'}</i>{label} <em>{value}</em></span>)}</div>
   <p className="fvVerdictLine">{verdictLine(r,en)}</p>
  </div>:<p className="fvFound">{en?'Loading the latest signals…':'正在读取最新信号…'}</p>}
 </div>;
}

export default function FirstVisit({rows,onClose}:{rows:SignalRow[]|null;onClose:()=>void}) {
 const {locale}=useLocale(), en=locale==='en';
 useEffect(()=>{markSeen();trackEvent('intro_viewed')},[]);
 const since=useCountUp(rows?rows.filter(r=>r.week>=RULE_LOCKED).length:null);
 const closedCount=rows?rows.filter(r=>r.status==='closed').length:null;
 const closed=useCountUp(closedCount);
 const act=(target:string)=>()=>trackEvent('intro_action',{target});
 return <section className="fvHero" aria-labelledby="fvTitle">
  <button type="button" className="fvClose" aria-label={en?'Hide the intro':'收起介绍'} onClick={()=>{trackEvent('intro_closed');onClose()}}>×</button>
  <div className="fvCopy">
   <h1 id="fvTitle">{en?'Buy the bottoms that hold. Risk 1 to aim for 3.':'抄守住的底，亏 1 博 3。'}</h1>
   {/* The 3R exit means about one win in four breaks even (before costs and time exits). */}
   <p>{en?'Stop just below, target 3× the risk: right about 1 time in 4 breaks even.':'止损就在底下，目标 3 倍风险：大约 4 次对 1 次就打平。'}</p>
   <div className="fvProof">
    <div><b>{since??'—'}</b><span>{en?'signals so far':'个信号'}</span></div>
    <div><b>{closed??'—'}<small> / 100</small></b><span>{en?'trades closed':'笔已平仓'}</span></div>
    <div className="fvVerdict"><b>{closedCount!==null&&closedCount>=100?(en?'Verdict due':'该下结论了'):(en?'Not proven yet':'还没证明')}</b></div>
   </div>
   <div className="fvActions">
    <a className="fvMain" href="/signals" onClick={act('signals')}>{en?'See this week’s signals →':'看本周信号 →'}</a>
    <a href="/learn" onClick={act('learn')}>{en?'How it works':'怎么做的'}</a>
    <a className="fvPlain" href="https://freddyliang.com" target="_blank" rel="noopener noreferrer" onClick={act('builder')}>{en?'Who built this ↗':'谁做的 ↗'}</a>
   </div>
  </div>
  <Film rows={rows} en={en}/>
 </section>;
}
