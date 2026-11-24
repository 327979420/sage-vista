'use client';
import {useEffect,useState} from 'react';
import {Localized,useLocale} from '../i18n/locale';
import {translate} from '../i18n/messages';
import {steps} from './learn';
import {validTicket} from '../evidence/data';
import {useEvidence} from '../evidence/shared';
import SignalChart,{chartInput} from '../app/signal-chart';

// Learn, terminal view: the four steps of 3W on one real trade (the published historical example,
// Agilent 2012). The weekly chart draws itself; each step lights its part (pattern, order, stop and
// target), and the last step shows the payoff of ten trades. It plays by itself.
// Step titles without their "Step n ·" prefix, translated first so the catalog entry matches.
const short = (title:string, locale:'zh'|'en') => translate(title,locale).replace(/^(第 \d 步|Step \d) · /,'');
const PAYOFF = [3,-1,-1,3,-1,-1,3,-1,3,-1]; // four winners at +3R, six losers at -1R: about the 40% win rate of the backtest
const TOTAL = PAYOFF.reduce((a,b)=>a+b,0);

export default function LearnStepper() {
 const {locale}=useLocale(), en=locale==='en';
 const [step,setStep]=useState(0);
 const [auto,setAuto]=useState(true);
 const ticket=useEvidence('/app/ticket-example.json',validTicket).data, example=ticket?chartInput(ticket):null;
 useEffect(()=>{if(!auto)return;if(typeof window!=='undefined'&&window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)return;const id=setInterval(()=>setStep(s=>(s+1)%4),6000);return()=>clearInterval(id)},[auto]);
 const pick=(i:number)=>{setAuto(false);setStep(i)};
 return <div className="ovRoot">
  <section className="ovHead"><div>
   <h1>{en?'3W in four steps, on a real trade.':'四步看懂 3W，用一笔真实的单子。'}</h1>
  </div></section>
  <div className="lnSteps" role="tablist" aria-label={en?'Steps':'步骤'}>{steps.map(([title],i)=><button key={title} type="button" role="tab" aria-selected={i===step} onClick={()=>pick(i)}><small>0{i+1}</small>{short(title,locale)}{i===step&&auto&&<i className="lnTimer" key={`t${step}`}/>}</button>)}</div>
  <div className="ovGrid lnGrid">
   <section className="ovPanel lnChart" data-step={step} aria-label={en?'Example chart':'例子图'}>
    {step<3?<div className="lnReal" data-step={step}>{example?<><SignalChart r={example} en={en}/>
     <p className="lnCaption">{en?`Agilent (A), week of ${example.week}: filled, then stopped out for −1R.`:`Agilent（A）· ${example.week} 周：成交后跌到止损，亏 1R。`}</p></>
     :<p className="lnCaption">{en?'Loading the example…':'正在读取例子…'}</p>}</div>:<div className="lnPayoff">
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
