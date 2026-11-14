'use client';
import {useEffect,useState} from 'react';
import {Localized,useLocale} from '../i18n/locale';
import {translate} from '../i18n/messages';
import {steps} from './learn';

// Learn, terminal view: the four steps of 3W drawn on one schematic weekly chart. Each step lights
// its part (pattern, order, stop and target, the payoff of ten trades). A diagram, not real prices.
const PRICE = 'M20 40 L60 110 L80 60 L130 175 L150 230 L200 150 L220 95 L265 190 L290 232 L335 175 L360 125 L395 200 L420 228 L470 180';
// Step titles without their "Step n ·" prefix, translated first so the catalog entry matches.
const short = (title:string, locale:'zh'|'en') => translate(title,locale).replace(/^(第 \d 步|Step \d) · /,'');
const PAYOFF = [3,-1,-1,3,-1,-1,3,-1,3,-1]; // four winners at +3R, six losers at -1R: about the 40% win rate of the backtest
const TOTAL = PAYOFF.reduce((a,b)=>a+b,0);

export default function LearnStepper() {
 const {locale}=useLocale(), en=locale==='en';
 const [step,setStep]=useState(0);
 const [auto,setAuto]=useState(true);
 useEffect(()=>{if(!auto)return;if(typeof window!=='undefined'&&window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)return;const id=setInterval(()=>setStep(s=>(s+1)%4),6000);return()=>clearInterval(id)},[auto]);
 const pick=(i:number)=>{setAuto(false);setStep(i)};
 return <div className="ovRoot">
  <section className="ovHead"><div>
   <small>{en?'Research · Learn':'研究 · 学习'}</small>
   <h1>{en?'3W in four steps, on one chart.':'一张图，四步看懂 3W。'}</h1>
   <p>{en?'Click a step, or let it play. The chart is a diagram of the rule, not real prices.':'点任意一步，或让它自己播放。图是规则的示意图，不是真实价格。'}</p>
  </div></section>
  <div className="lnSteps" role="tablist" aria-label={en?'Steps':'步骤'}>{steps.map(([title],i)=><button key={title} type="button" role="tab" aria-selected={i===step} onClick={()=>pick(i)}><small>0{i+1}</small>{short(title,locale)}{i===step&&auto&&<i className="lnTimer" key={`t${step}`}/>}</button>)}</div>
  <div className="ovGrid lnGrid">
   <section className="ovPanel lnChart" data-step={step} aria-label={en?'Diagram':'示意图'}>
    {step<3?<svg viewBox="0 0 600 300" aria-hidden="true">
     <path className="lnPrice" d={PRICE}/>
     <g className="lnS0"><line x1="60" y1="70" x2="470" y2="150" className="lnTrend"/>{[[80,60],[220,95],[360,125]].map(([x,y],i)=><g key={x}><circle cx={x} cy={y} r="5" className="lnPush"/><text x={x} y={y-12} textAnchor="middle">{en?`push ${i+1}`:`推 ${i+1}`}</text></g>)}
      <line x1="140" y1="232" x2="440" y2="232" className="lnFloor"/>{[[150,230],[290,232],[420,228]].map(([x,y])=><circle key={x} cx={x} cy={y} r="5" className="lnBottom"/>)}<text x="440" y="252" textAnchor="end">{en?'flat bottoms':'平底'}</text>
      <circle cx="470" cy="180" r="7" className="lnSignal"/><text x="480" y="176">{en?'signal week':'信号周'}</text></g>
     <g className="lnS1"><line x1="470" y1="190" x2="590" y2="190" className="lnLimit"/><text x="590" y="184" textAnchor="end">{en?'limit −2%, 40 sessions':'挂单 −2%，等 40 天'}</text></g>
     <g className="lnS2"><line x1="470" y1="240" x2="590" y2="240" className="lnStopLine"/><text x="590" y="256" textAnchor="end">{en?'stop: 1% under last bottom':'止损：最后一个底下方 1%'}</text>
      <rect x="560" y="190" width="18" height="50" className="lnRisk"/><text x="552" y="218" textAnchor="end">1R</text>
      <line x1="470" y1="40" x2="590" y2="40" className="lnTarget"/><rect x="560" y="40" width="18" height="150" className="lnReward"/><text x="552" y="110" textAnchor="end">3R</text><text x="590" y="32" textAnchor="end">{en?'target 3R':'目标 3R'}</text></g>
    </svg>:<div className="lnPayoff">
     <p>{en?'Ten trades at about the backtest’s 40% win rate:':'按回测大约 40% 的胜率，假设做 10 笔：'}</p>
     <div className="lnBars">{PAYOFF.map((v,i)=><div key={i} style={{animationDelay:`${i*0.18}s`}}><i data-up={v>0||undefined} style={{height:`${Math.abs(v)*22}px`}}/><small>{v>0?'+3R':'−1R'}</small></div>)}</div>
     <p className="lnSum">{en?`4 × +3R and 6 × −1R = `:'4 × +3R 加 6 × −1R = '}<b>+{TOTAL}R</b>{en?' before costs. Losing often is part of the plan; the stop keeps each loss small.':'（未扣成本）。经常亏是计划的一部分，止损让每次只亏一点。'}</p>
    </div>}
   </section>
   <section className="ovPanel lnText" aria-live="polite"><small>{en?`Step ${step+1} of 4`:`第 ${step+1} 步 / 共 4 步`}</small><h3>{short(steps[step][0],locale)}</h3><Localized><p>{steps[step][1]}</p></Localized>
    <div className="lnNav"><button type="button" onClick={()=>pick((step+3)%4)}>← {en?'Back':'上一步'}</button><button type="button" onClick={()=>pick((step+1)%4)}>{en?'Next':'下一步'} →</button></div></section>
  </div>
 </div>;
}
