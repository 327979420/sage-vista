'use client';
import {useEffect,useMemo,useState,type ReactNode} from 'react';
import {useLocale} from '../i18n/locale';
import type {Today} from './data';
import {closeAt,scanDay,type SignalRow} from './signal-rows';
import CrawlWeb from './crawl-web';
import Term from '../term';

// Terminal overview on top of Today: one headline, today's run as one track, the market light as a
// field of stocks, a replay of the latest scan, the road to proof and two folds. Public data only.
type Props = {today:Today|null; rows:SignalRow[]|null};

function useNow(ms=1000) {
 const [now,setNow]=useState<number|null>(null);
 useEffect(()=>{const first=setTimeout(()=>setNow(Date.now()),0),id=setInterval(()=>setNow(Date.now()),ms);return()=>{clearTimeout(first);clearInterval(id)}},[ms]);
 return now;
}
function useReady(delay=150) {const [ready,setReady]=useState(false);useEffect(()=>{const id=setTimeout(()=>setReady(true),delay);return()=>clearTimeout(id)},[delay]);return ready}
// Stable pseudo-random order so the same stocks light up on every visit.
const shuffled = (n:number) => {const a=[...Array(n).keys()];let seed=297;for(let i=n-1;i>0;i--){seed=(seed*16807)%2147483647;const j=seed%(i+1);[a[i],a[j]]=[a[j],a[i]]}return a};
const pad = (v:number) => String(v).padStart(2,'0');

export function Countdown({target,en}:{target:number;en:boolean}) {
 const now=useNow();
 if(now===null)return <b className="ovCount">--:--:--</b>;
 const left=Math.max(0,target-now), d=Math.floor(left/86400000);
 return <b className="ovCount">{d>0&&<>{d}<small>{en?'d':'天'}</small> </>}{pad(Math.floor(left/3600000)%24)}:{pad(Math.floor(left/60000)%60)}:{pad(Math.floor(left/1000)%60)}</b>;
}

// Today's run as one track (GitLab-style stage graph): each stage shows one real number;
// stages before the stop are green, the stop is amber, later ones grey. A dot runs to the stop.
function RunTrack({today,rows,en}:{today:Today;rows:SignalRow[];en:boolean}) {
 const ready=useReady(250);
 const week=rows.map(r=>r.week).sort().at(-1)??'';
 const latest=rows.filter(r=>r.week===week);
 const passed=latest.filter(r=>r.ruleOk), placed=passed.filter(r=>r.gateOk);
 const open=rows.filter(r=>r.status==='open').length, closed=rows.filter(r=>r.status==='closed').length;
 const rrFail=latest.filter(r=>r.rrOk===false).length, vetoed=latest.filter(r=>r.veto).length;
 const green=today.market.light==='green', breadth=today.market.breadth;
 const nodes:[string,string,string][]=[
  [en?'Prices':'行情', today.as_of.slice(5), en?'closes in':'收盘数据'],
  [en?'Shapes':'形态', String(latest.length), en?'triangles found':'个三角形'],
  [en?'Rule':'规则', String(passed.length), en?'passed':'个通过'],
  [en?'Market light':'市场灯', green?(en?'Green':'绿'):(en?'Amber':'黄'), breadth===null?'':(en?`${(breadth*100).toFixed(1)}%, needs 50%`:`${(breadth*100).toFixed(1)}%，要过 50%`)],
  [en?'Orders':'下单', String(placed.length), en?'placed':'笔'],
  [en?'Open':'持仓', String(open), en?'positions':'笔'],
  [en?'Record':'记录', String(closed), en?'of 100 closed':'/ 100 笔平仓'],
 ];
 const stop=!latest.length?1:!passed.length?2:!placed.length?3:!open?5:6;
 const reasons:string[]=[];
 if(stop===2){
  if(rrFail)reasons.push(rrFail===latest.length?(en?`all ${rrFail} had reward/risk under 1.5`:`${rrFail} 个盈亏比都不到 1.5`):(en?`${rrFail} had reward/risk under 1.5`:`${rrFail} 个盈亏比不到 1.5`));
  if(vetoed)reasons.push(en?`${vetoed} monthly veto`:`${vetoed} 个月线否决`);
 }
 const why=stop===1?(en?'No triangle that week.':'那周没有三角形。')
  :stop===2?(en?`Stopped at Rule: ${reasons.join(', ')}.`:`停在规则：${reasons.join('，')}。`)
  :stop===3?(en?'Stopped at Market light: under half the pool was above its 200-day line that week.':'停在市场灯：那周股票池站上 200 日线的不到一半。')
  :stop===5?(en?`${placed.length} orders placed, waiting to fill.`:`已挂 ${placed.length} 单，等成交。`)
  :(en?`${open} open; closed trades count toward the record.`:`${open} 笔持仓，平仓后计入记录。`);
 const state=(i:number)=>i<stop?'go':i===stop?'wait':'off';
 return <section className="ovPanel ovRun" aria-label={en?'Today’s run':'今天的流程'}>
  <header><small>{en?`Today’s run · week of ${week.slice(5)}`:`今天的流程 · ${week.slice(5)} 周`}</small></header>
  <ol className="ovTrack" style={{['--stop' as string]:`${stop/nodes.length*100}%`}} data-ready={ready||undefined}>
   <i className="ovRunner" aria-hidden="true"/>
   {nodes.map(([name,value,unit],i)=><li key={name} data-s={state(i)} aria-current={i===stop?'step':undefined}><small>{name}</small><b>{value}</b><span>{unit}</span></li>)}
  </ol>
  <p className="ovStop">{why}</p>
 </section>;
}

// Goal-gradient progress to the 100-trade verdict, with the 30 and 60 checks marked.
function ProofRoad({rows,en}:{rows:SignalRow[];en:boolean}) {
 const closed=rows.filter(r=>r.status==='closed').length, next=[30,60,100].find(c=>c>closed)??100;
 return <section className="ovPanel ovProof" aria-label={en?'Road to proof':'证明进度'}>
  <header><small>{en?'Road to proof':'证明进度'}</small><a href="/forward">{en?'Forward record →':'前向记录 →'}</a></header>
  <div className="ovProofBar"><em style={{width:`${Math.min(100,closed)}%`}}/>{[30,60,100].map(c=><i key={c} style={{left:`${c}%`}} data-done={closed>=c||undefined}><span>{c===100?(en?'100 · proof':'100 · 证明'):(en?`${c} · check`:`${c} · 检查`)}</span></i>)}</div>
  <p>{en?`${closed} closed so far. Next: ${next}.`:`已平仓 ${closed} 笔，下一站 ${next}。`}</p>
 </section>;
}

function GateField({today,en}:{today:Today;en:boolean}) {
 const m=today.market, sample=m.breadth_sample??0, lit=m.breadth===null?0:Math.round(m.breadth*sample);
 const order=useMemo(()=>shuffled(sample),[sample]);
 const [shown,setShown]=useState(0);
 useEffect(()=>{
  // Light the stocks a few at a time; with reduced motion they all appear on the first tick.
  const step=typeof window!=='undefined'&&window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?lit:6;
  let n=0;const id=setInterval(()=>{n=Math.min(lit,n+step);setShown(n);if(n>=lit)clearInterval(id)},30);return()=>clearInterval(id);
 },[lit]);
 const on=useMemo(()=>new Set(order.slice(0,shown)),[order,shown]);
 const green=m.light==='green';
 return <section className="ovPanel ovGate" aria-label={en?'Market light':'市场灯'}>
  <header><small><Term k="light">{en?'Market light':'市场灯'}</Term></small><span data-tone={green?'go':'wait'}>{green?(en?'Green':'绿灯'):(en?'Amber':'黄灯')}</span></header>
  <div className="ovGateTop"><b>{m.breadth===null?'—':`${(m.breadth*100).toFixed(1)}%`}</b>
   <p>{en?`${lit} of ${sample} 3W stocks are above their 200-day line. Over half are needed.`:`3W 股票池 ${sample} 只里，有 ${lit} 只站上 200 日线。要过半才放行。`}</p></div>
  <div className="ovDots" aria-hidden="true">{order.map((_,i)=><i key={i} data-on={on.has(i)||undefined}/>)}</div>
  <p className="ovNote"><span data-tone={m.spy_over_200d?'go':'wait'}>{m.spy_over_200d?'✓':'✕'}</span> {en?`SPY ${m.distance_pct===null?'':`${m.distance_pct>0?'+':''}${m.distance_pct.toFixed(1)}%`} vs its 200-day line`:`SPY 距 200 日线 ${m.distance_pct===null?'—':`${m.distance_pct>0?'+':''}${m.distance_pct.toFixed(1)}%`}`}<span className="ovDate">{today.as_of}</span></p>
 </section>;
}

function ScanReplay({rows,en}:{rows:SignalRow[];en:boolean}) {
 const [run,setRun]=useState(0);
 const week=rows.map(r=>r.week).sort().at(-1), latest=rows.filter(r=>r.week===week);
 if(!week)return null;
 const steps=(r:SignalRow):[string,boolean|null,string][]=>[
  [en?'Shape':'形态',r.shapePassed===r.shapeTotal,`${r.shapePassed}/${r.shapeTotal}`],
  [en?'Monthly':'月线',r.veto===null?null:!r.veto,r.veto?(en?'veto':'否决'):(en?'ok':'通过')],
  [en?'Reward/risk':'盈亏比',r.rrOk,r.rr===null?'—':r.rr.toFixed(2)],
  [en?'Market':'大盘',r.gateOk,r.breadth===null?'—':`${(r.breadth*100).toFixed(1)}%`],
 ];
 return <section className="ovPanel ovReplay" aria-label={en?'Latest scan replay':'最近一次扫描回放'}>
  <header><small>{en?`Latest scan · week of ${week.slice(5)}`:`最近一次扫描 · ${week.slice(5)} 周`}</small><button type="button" onClick={()=>setRun(v=>v+1)}>↻ {en?'Replay':'重放'}</button></header>
  <ol key={run}>{latest.map((r,i)=><li key={r.id}>
   <b>{r.symbol}</b>
   {steps(r).map(([label,ok,value],j)=><span key={label} className="ovStep" data-ok={ok===null?undefined:String(ok)} style={{animationDelay:`${(i*4+j)*0.28}s`}}><em>{ok===null?'·':ok?'✓':'✕'}</em>{label} <i>{value}</i></span>)}
  </li>)}</ol>
 </section>;
}

function Pipeline({today,rows,en}:{today:Today;rows:SignalRow[]|null;en:boolean}) {
 const [sel,setSel]=useState(1);
 const green=today.market.light==='green', open=rows?.filter(r=>r.status==='open').length??0, closed=rows?.filter(r=>r.status==='closed').length??0;
 const S:[string,string,string,string][]=[
  [en?'Prices':'行情', en?'OK':'正常', 'go', en?'After each US close the daily bars are pulled; only date-checked data is published.':'每天美股收盘后拉取日线，日期核对无误才发布。'],
  [en?'Weekly scan':'周扫描', scanDay(today.signal_week).slice(5), 'wait', en?'The locked rule looks for weekly triangles. A week is only readable after the first session of the week after next.':'用锁定的规则找周线三角。一周的信号要到下下周第一个交易日收盘后才认得出。'],
  [en?'Market light':'市场灯', green?(en?'Green':'绿灯'):(en?'Amber':'黄灯'), green?'go':'wait', en?'Orders only when SPY is above its 200-day line and over half the pool is too, judged on the signal week.':'SPY 在 200 日线上方，且股票池过半站上 200 日线，才放行。看的是信号那一周。'],
  [en?'Order':'下单', en?'Waiting':'等信号', 'dim', en?'Limit order 2% under the signal close, valid 40 sessions; stop 1% under the last bottom; skip if reward/risk is under 1.5.':'在信号收盘价下方 2% 挂限价单，最多等 40 个交易日；止损在最后一个底下方 1%；盈亏比不到 1.5 不做。'],
  [en?'Exit':'平仓', open?(en?`${open} open`:`${open} 持仓`):(en?'None':'无持仓'), 'dim', en?'Exit at 3R or after 130 sessions; results in net R after 0.1% per side.':'到 3R 止盈或持有满 130 个交易日离场，按扣成本后的净 R 记。'],
  [en?'Scoring':'判卷', `${closed} / 30`, 'dim', en?'Checked every 30 trades. Proven at 100 if the result is unlikely to be luck; alarm if clearly losing.':'每满 30 笔检查一次。满 100 笔且结果不像运气才算证明；明显亏损就报警。'],
  [en?'Paper account':'模拟账户', en?'Running':'运行中', 'go', en?'Core 50% follows the sector trend basket, rebalanced monthly; satellite 50% trades 3W signals.':'核心 50% 跟行业趋势篮子，每月底调仓；卫星 50% 按 3W 信号下单。'],
 ];
 return <section className="ovPanel ovPipe" aria-label={en?'Daily pipeline':'每日流程'}>
  <header><small>{en?'Click a step':'点一步看说明'}</small></header>
  <div className="ovStations">{S.map(([name,status,tone],i)=><button key={name} type="button" aria-pressed={i===sel} onClick={()=>setSel(i)}>
   <small>{pad(i+1)}</small><b>{name}</b><span data-tone={tone}>{status}</span></button>)}</div>
  <p className="ovExplain"><b>{S[sel][0]}</b> {S[sel][3]}</p>
 </section>;
}

// Secondary detail stays folded; its content mounts on open, so the scan map's sweep plays then.
function Fold({title,children}:{title:string;children:ReactNode}) {
 const [open,setOpen]=useState(false);
 return <details className="ovFold" onToggle={e=>setOpen(e.currentTarget.open)}><summary>{title}</summary>{open&&children}</details>;
}

export default function Overview({today,rows}:Props) {
 const {locale}=useLocale(), en=locale==='en';
 if(!today)return null;
 const green=today.market.light==='green', next=scanDay(today.signal_week);
 return <div className="ovRoot">
  <section className="ovHead">
   <div>
    <small>{en?'3W · Today':'3W · 今日'}</small>
    <h1><Term k="light">{en?'Market light':'市场灯'}</Term>{green?(en?' is green. Waiting for the next scan.':'是绿的，等下一次扫描。'):(en?' is amber: new signals won’t be ordered.':'是黄的：新信号不下单。')}</h1>
    <p>{today.orders_to_place?(en?`${today.orders_to_place} orders to place.`:`待下单 ${today.orders_to_place} 个。`):(en?'Nothing to do today.':'今天不用动。')}</p>
   </div>
   <div className="ovNext"><small>{en?`Next scan · after the ${next.slice(5)} close`:`下一次扫描 · ${next.slice(5)} 收盘后`}</small><Countdown target={closeAt(next)} en={en}/></div>
  </section>
  {rows&&<RunTrack today={today} rows={rows} en={en}/>}
  <div className="ovGrid"><GateField today={today} en={en}/>{rows&&<ScanReplay rows={rows} en={en}/>}</div>
  {rows&&<ProofRoad rows={rows} en={en}/>}
  <Fold title={en?'How a day runs':'每天怎么跑'}><Pipeline today={today} rows={rows} en={en}/></Fold>
  <Fold title={en?'Multi-factor scan map':'多因子扫描图'}><CrawlWeb en={en}/></Fold>
 </div>;
}
