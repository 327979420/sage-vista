'use client';
import {useEffect,useMemo,useState} from 'react';
import {useLocale} from '../i18n/locale';
import type {Today} from './data';
import {closeAt,scanDay,type SignalRow} from './signal-rows';
import CrawlWeb from './crawl-web';
import Term from '../term';

// Terminal overview on top of Today: one headline, the signal funnel, the market gate as a
// field of stocks, a replay of the latest scan and the daily pipeline. Public data only.
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

function Funnel({rows,en}:{rows:SignalRow[];en:boolean}) {
 const ready=useReady();
 const rule=rows.filter(r=>r.ruleOk), gate=rule.filter(r=>r.gateOk), filled=rows.filter(r=>r.filled), closed=rows.filter(r=>r.status==='closed');
 const rrFail=rows.filter(r=>r.rrOk===false).length, vetoed=rows.filter(r=>r.veto).length;
 const cells:[string,number,string,string][]=[
  [en?'3W signals':'3W 信号', rows.length, en?`${new Set(rows.map(r=>r.week)).size} weeks`:`${new Set(rows.map(r=>r.week)).size} 周`, 'ink'],
  [en?'Passed the rule':'过了规则', rule.length, en?`${rrFail} reward/risk too low · ${vetoed} monthly veto`:`${rrFail} 个盈亏比不够 · ${vetoed} 个月线否决`, 'ink'],
  [en?'Market let through':'大盘放行', gate.length, en?'over half the pool above its 200-day that week':'那周股票池过半站上 200 日线', gate.length?'go':'wait'],
  [en?'Filled':'成交', filled.length, en?'limit buy 2% under the close':'收盘价下方 2% 挂买单', 'dim'],
  [en?'Closed':'已平仓', closed.length, en?'first check at 30':'第一次检查在 30 笔', 'dim'],
  [en?'Needed for proof':'证明需要', 100, en?'closed trades, not luck':'笔平仓，且不像运气', 'dim'],
 ];
 return <div className="ovFunnel" role="list" aria-label={en?'Signal funnel':'信号漏斗'}>
  {cells.map(([label,value,sub,tone],i)=><div key={label} role="listitem" data-tone={tone} style={{transitionDelay:`${i*90}ms`}} data-ready={ready||undefined}>
   <small>{label}</small><b>{value}</b><span>{sub}</span>{i<cells.length-1&&<i aria-hidden="true">›</i>}
  </div>)}
 </div>;
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
  <header><small>01 · <Term k="light">{en?'Market light':'市场灯'}</Term></small><span data-tone={green?'go':'wait'}>{green?(en?'Green':'绿灯'):(en?'Amber':'黄灯')}</span></header>
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
 const placed=latest.filter(r=>r.ruleOk&&r.gateOk).length;
 return <section className="ovPanel ovReplay" aria-label={en?'Latest scan replay':'最近一次扫描回放'}>
  <header><small>{en?`02 · Replay · week of ${week.slice(5)}, read after the ${scanDay(week).slice(5)} close`:`02 · 回放 · ${week.slice(5)} 周，${scanDay(week).slice(5)} 收盘后认出`}</small><button type="button" onClick={()=>setRun(v=>v+1)}>↻ {en?'Replay':'重放'}</button></header>
  <ol key={run}>{latest.map((r,i)=><li key={r.id}>
   <b>{r.symbol}</b>
   {steps(r).map(([label,ok,value],j)=><span key={label} className="ovStep" data-ok={ok===null?undefined:String(ok)} style={{animationDelay:`${(i*4+j)*0.28}s`}}><em>{ok===null?'·':ok?'✓':'✕'}</em>{label} <i>{value}</i></span>)}
  </li>)}</ol>
  <p className="ovNote">{en?`Done · ${latest.length} signals · ${latest.filter(r=>r.ruleOk).length} passed the rule · ${placed} orders`:`完成 · ${latest.length} 个信号 · ${latest.filter(r=>r.ruleOk).length} 个规则可做 · ${placed} 单`}</p>
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
  <header><small>{en?'04 · How a day runs · click a step':'04 · 每天怎么跑 · 点一步看说明'}</small></header>
  <div className="ovStations">{S.map(([name,status,tone],i)=><button key={name} type="button" aria-pressed={i===sel} onClick={()=>setSel(i)}>
   <small>{pad(i+1)}</small><b>{name}</b><span data-tone={tone}>{status}</span></button>)}</div>
  <p className="ovExplain"><b>{S[sel][0]}</b> {S[sel][3]}</p>
 </section>;
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
    <p>{en?`${today.new_signals_this_week} new signals this week, ${today.orders_to_place} orders to place.`:`本周新信号 ${today.new_signals_this_week} 个，待下单 ${today.orders_to_place} 个。`}</p>
   </div>
   <div className="ovNext"><small>{en?`Next scan · week of ${today.signal_week.slice(5)} · after the ${next.slice(5)} close`:`下一次扫描 · ${today.signal_week.slice(5)} 周 · ${next.slice(5)} 收盘后`}</small><Countdown target={closeAt(next)} en={en}/></div>
  </section>
  {rows&&<Funnel rows={rows} en={en}/>}
  <div className="ovGrid"><GateField today={today} en={en}/>{rows&&<ScanReplay rows={rows} en={en}/>}</div>
  <CrawlWeb en={en}/>
  <Pipeline today={today} rows={rows} en={en}/>
 </div>;
}
