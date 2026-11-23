'use client';
import {useEffect,useState,type CSSProperties} from 'react';
import {useLocale} from '../i18n/locale';
import {trackEvent} from '../analytics';
import {markSeen,RULE_LOCKED} from '../first-visit';
import type {SignalRow} from './signal-rows';

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

function Replay({rows,en}:{rows:SignalRow[]|null;en:boolean}) {
 const [run,setRun]=useState(0);
 const [pick,setPick]=useState<string|null>(null);
 const week=rows?.map(r=>r.week).sort().at(-1);
 const latest=rows&&week?rows.filter(r=>r.week===week):[];
 const passed=latest.filter(r=>r.ruleOk).length, ordered=latest.filter(r=>r.ruleOk&&r.gateOk).length;
 const picked=latest.find(r=>r.id===pick);
 const result=!latest.length?'':ordered?(en?`${ordered} became orders.`:`${ordered} 个下单。`)
  :passed?(en?`${passed} passed the rule; the market light held them back.`:`${passed} 个过了规则，被市场灯拦下。`)
  :(en?`0 of ${latest.length} passed. The rule waits for reward/risk of 1.5 or more.`:`${latest.length} 个都没过。规则要盈亏比至少 1.5。`);
 const done={'--n':latest.length} as CSSProperties;
 return <div className="fvReplay" key={run} style={done}>
  <header><small>{en?'This week’s scan, replayed':'本周扫描回放'}</small><button type="button" onClick={()=>{setRun(v=>v+1);setPick(null);trackEvent('intro_replay')}}>↻ {en?'Replay':'重放'}</button></header>
  <svg className="fvPattern" viewBox="0 0 420 140" role="img" aria-label={en?'Sketch of the pattern: falling highs, flat bottoms, then a break above the line':'形态示意：高点一个比一个低，底部持平，然后向上突破'}>
   <line className="fvGuide" x1="8" y1="22" x2="330" y2="102.5"/>
   <line className="fvGuide fvFlat" x1="40" y1="113" x2="292" y2="113"/>
   <polyline className="fvLine" pathLength="1" points="8,22 58,112 112,48 166,112 220,75 272,112 318,92 362,62 412,34"/>
   <circle className="fvSignal" cx="318" cy="92" r="5"/>
   <text className="fvLabel" x="44" y="16">{en?'falling highs':'高点下降'}</text>
   <text className="fvLabel" x="120" y="132">{en?'flat bottoms':'底部持平'}</text>
   <text className="fvLabel fvLabelGo" x="330" y="108">{en?'break':'突破'}</text>
  </svg>
  {week?<>
   <p className="fvFound">{en?`Week of ${week.slice(5)}: ${latest.length} triangles found`:`${week.slice(5)} 周：找到 ${latest.length} 个三角形`}</p>
   <div className="fvChips">{latest.map((r,i)=><button key={r.id} type="button" aria-pressed={pick===r.id} aria-label={`${r.symbol}: ${checks(r,en).map(([label,ok])=>`${label} ${ok?'✓':'✕'}`).join(', ')}`} style={{'--i':i} as CSSProperties} onClick={()=>{setPick(pick===r.id?null:r.id);trackEvent('intro_stock',{symbol:r.symbol})}}>
    <b>{r.symbol}</b><span aria-hidden="true">{checks(r,en).map(([label,ok],j)=><i key={label} data-ok={ok===null?undefined:String(ok)} style={{'--j':j} as CSSProperties}>{ok===null?'·':ok?'✓':'✕'}</i>)}</span>
   </button>)}</div>
   <p className="fvResult" aria-live="polite">{picked?<><b>{picked.symbol}</b> {checks(picked,en).map(([label,ok,value])=>`${label} ${value} ${ok?'✓':'✕'}`).join(' · ')}</>:result}</p>
   <small className="fvHint">{en?'Tap a stock to see its checks.':'点一只股票看它的检查。'}</small>
  </>:<p className="fvFound">{en?'Loading this week’s scan…':'正在读取本周扫描…'}</p>}
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
   <span className="fvEyebrow">{en?'Rules, not predictions · tested in public':'不靠预测，靠规则 · 公开检验'}</span>
   <h1 id="fvTitle">{en?'Buy the bottoms that hold. Risk 1 to aim for 3.':'抄守住的底，亏 1 博 3。'}</h1>
   {/* The 3R exit means about one win in four breaks even (before costs and time exits). */}
   <p>{en?'Stop just below, target 3× the risk: right about 1 time in 4 breaks even.':'止损就在底下，目标 3 倍风险：大约 4 次对 1 次就打平。'}</p>
   <div className="fvProof">
    <div><b>{since??'—'}</b><span>{en?'signals since the lock':'锁定后的信号'}</span></div>
    <div><b>{closed??'—'}<small> / 100</small></b><span>{en?'closed trades needed for a verdict':'下结论要平仓 100 笔'}</span></div>
    <div className="fvVerdict"><b>{closedCount!==null&&closedCount>=100?(en?'Verdict due':'该下结论了'):(en?'Not proven yet':'还没证明')}</b><span>{en?'checked every Friday close':'每周五收盘后检查'}</span></div>
   </div>
   <div className="fvActions">
    <a className="fvMain" href="/signals" onClick={act('signals')}>{en?'See this week’s signals →':'看本周信号 →'}</a>
    <a href="/learn" onClick={act('learn')}>{en?'How it works · 4 steps':'四步看懂'}</a>
    <a className="fvPlain" href="https://freddyliang.com" target="_blank" rel="noopener noreferrer" onClick={act('builder')}>{en?'Who built this ↗':'谁做的 ↗'}</a>
   </div>
  </div>
  <Replay rows={rows} en={en}/>
 </section>;
}
