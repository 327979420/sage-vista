'use client';
import {useEffect,useState} from 'react';
import {useLocale} from '../i18n/locale';
import type {Forward} from '../evidence/data';

// Forward record, terminal view: how far from proof, what happened to every signal, and the
// evidence so far. Reads forward.json and record.json, both already public.
type Fact = {id:string;label:string;period:string|null;trades:number|null;p:number|null;verdict:string|null;note:string;average_R?:number|null;win_rate?:number|null};
type RecordFile = {facts:Fact[]};
export const FACTS_EN:Record<string,[string,string]> = {
 'locked-exam-3w':['Locked-data exam','Hints in the backtest, not independently proven.'],
 'backtest-2005-2025':['Development backtest (conservative)','The data 3W was built on; reference only.'],
 'factor-attribution':['Excess return after common factors','A hint, not significant (t under 2).'],
 'hk-exam-a':['Hong Kong exam','Too few trades; only “not proven”.'],
 'locked-exam-sector':['Sector trend basket','Useful, though SPY trend alone did better in this period.'],
 'locked-exam-core-satellite':['Core + satellite','Useful, mostly from diversification and low exposure; it does not prove 3W stock picking.'],
 'locked-exam-limits':['Exam limits','Survivorship in the stock pool; the basket exam covers about five years.'],
 'forward-expectation':['Development trades entering the account','Development data, account trades only; a reference, not a promise.'],
};
const validRecord = (v:unknown):v is RecordFile => !!v&&typeof v==='object'&&Array.isArray((v as RecordFile).facts)&&(v as RecordFile).facts.every(f=>f&&typeof f.id==='string'&&typeof f.label==='string');
type Span = '1w'|'4w'|'13w';

export default function ForwardTerminal({data}:{data:Forward}) {
 const {locale}=useLocale(), en=locale==='en';
 const [record,setRecord]=useState<RecordFile|null>(null);
 const [span,setSpan]=useState<Span>('1w');
 const [sel,setSel]=useState<string|null>(null);
 const [open,setOpen]=useState<string|null>(null);
 const [ready,setReady]=useState(false);
 useEffect(()=>{let active=true;fetch('/app/record.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(d=>{if(active&&validRecord(d))setRecord(d)}).catch(()=>{});const t=setTimeout(()=>setReady(true),150);return()=>{active=false;clearTimeout(t)}},[]);
 const j=data.judging, t=j.thresholds, closed=data.summary.closed, goal=t.proof_min_trades;
 const count=(st:string)=>data.signals.filter(s=>s.status===st).length;
 const flow:[string,number,string,string][]=[
  [en?'Signals':'信号',data.signals.length,en?`${new Set(data.signals.map(s=>s.signal_week)).size} weeks`:`${new Set(data.signals.map(s=>s.signal_week)).size} 周`,'ink'],
  [en?'Skipped':'跳过',count('skipped'),en?'rules or gate said no':'规则或闸门没放行','wait'],
  [en?'Waiting to fill':'等成交',count('waiting'),en?'limit valid 40 sessions':'挂单 40 个交易日有效','dim'],
  [en?'Open':'持仓',count('open'),en?'3R target or 130 sessions':'目标 3R 或 130 天','dim'],
  [en?'Closed':'已平仓',closed,en?'counts toward proof':'计入成绩','dim'],
 ];
 const moves=data.signals.map(s=>({id:s.id,sym:s.symbol,week:s.signal_week,status:s.status,m:s.moves[span]?.move_pct??null,twin:s.random.moves?.[span]?.median_pct??null,n:s.random.moves?.[span]?.sample??null})).filter(x=>x.m!==null) as {id:string;sym:string;week:string;status:string;m:number;twin:number|null;n:number|null}[];
 const spans:Span[]=['1w','4w','13w'];
 const range=Math.max(10,...moves.map(x=>Math.ceil(Math.abs(x.m)/5)*5));
 const P=(v:number)=>50+Math.max(-range,Math.min(range,v))/range*50;
 const order=[...moves].sort((a,b)=>a.m-b.m);
 const x=moves.find(m=>m.id===sel)??moves[0];
 const verdict=j.verdict==='继续记录，未证明'?(en?'Still recording. Not proven.':'还在记录，没证明。'):j.verdict;
 return <div className="ovRoot">
  <section className="ovHead"><div>
   <small>{en?'3W · Forward record · after the rule froze':'3W · 前向记录 · 规则冻结之后'}</small>
   <h2>{verdict}</h2>
   <p>{en?`Only new signals after the freeze count. ${goal} closed trades with t ≥ ${t.proof_t_gte} prove it; a negative average with t ≤ ${t.alarm1_t_lte} raises an alarm.`:`只算规则冻结之后的新信号。平仓满 ${goal} 笔、t 值到 ${t.proof_t_gte} 才算证明有效；平均为负且 t 到 ${t.alarm1_t_lte} 就拉警报。`}</p>
  </div></section>
  <section className="ovPanel fwProof" aria-label={en?'Progress to proof':'证明进度'}>
   <header><small>{en?'01 · Closed trades':'01 · 平仓笔数'}</small><span className="fwNext">{en?`Checked ${data.next_check}`:'每周五收盘后检查'}</span></header>
   <b className="fwCount">{closed} <span>/ {goal}</span></b>
   <div className="fwTrack"><div className="fwFill" style={{width:`${ready?Math.min(100,closed/goal*100):0}%`}}/><i className="fwScan" aria-hidden="true"/>
    {t.checkpoints.map(c=><span key={c} className="fwCheck" style={{left:`${c/goal*100}%`}} data-final={c===goal||undefined}><em>{c} · {c===goal?(en?'proof':'证明门槛'):(en?'check':'检查')}</em></span>)}
    <span className="fwNow" style={{left:`${ready?Math.min(100,closed/goal*100):0}%`}}><em>{en?'now':'现在'}</em></span></div>
   <div className="ovFunnel fwFlow">{flow.map(([label,value,sub,tone],i)=><div key={label} data-tone={tone} data-ready={ready||undefined} style={{transitionDelay:`${i*90}ms`}}><small>{label}</small><b>{value}</b><span>{sub}</span></div>)}</div>
  </section>
  <div className="ovGrid fwGrid">
   <section className="ovPanel" aria-label={en?'Skipped signals afterwards':'没下单的信号后来怎样'}>
    <header><small>{en?'02 · What the signals did afterwards':'02 · 信号后来怎样'}</small>
     <span className="fwSpans" role="group" aria-label={en?'Period':'区间'}>{spans.map(s=><button key={s} type="button" aria-pressed={s===span} onClick={()=>setSpan(s)} disabled={!data.signals.some(r=>r.moves[s])}>{s==='1w'?(en?'1 week':'1 周'):s==='4w'?(en?'4 weeks':'4 周'):(en?'13 weeks':'13 周')}</button>)}</span></header>
    <p className="fwLead">{en?'Not traded, so not scored. They are still tracked, to check later whether the gate and rules stopped good or bad trades.':'没下单，不计成绩。照样跟踪，是为了以后检查闸门和规则挡掉的是好是坏。'}</p>
    {moves.length?<><div className="fwPlot">
     <span className="fwZero"/>{[-range,-range/2,0,range/2,range].map(v=><em key={v} className="fwAxis" style={{left:`${P(v)}%`}}>{v>0?'+':''}{v}%</em>)}
     {order.map((d,i)=><button key={d.id} type="button" className="fwDot" data-on={d.id===x?.id||undefined} data-up={d.m>=0||undefined} aria-label={`${d.sym} ${d.m.toFixed(1)}%`} onMouseEnter={()=>setSel(d.id)} onFocus={()=>setSel(d.id)} onClick={()=>setSel(d.id)}
      style={{left:`${ready?P(d.m):50}%`,top:`${50+(i%2?1:-1)*(9+(Math.floor(i/2)%4)*10)}%`}}><span>{d.sym}</span></button>)}
    </div>
    {x&&<div className="fwPick"><b>{x.sym}</b><span>{en?`week of ${x.week.slice(5)}`:`${x.week.slice(5)} 周`}</span><strong data-tone={x.m>=0?'go':'loss'}>{x.m>0?'+':''}{x.m.toFixed(1)}%</strong>
     <p>{x.twin!==null?(en?`A random sample of ${x.n} stocks from the same pool moved ${x.twin>0?'+':''}${x.twin.toFixed(1)}% (median) over the same time.`:`同期从同一个股票池随机抽 ${x.n} 只，中位数 ${x.twin>0?'+':''}${x.twin.toFixed(1)}%。`):(en?'No comparable random sample for this period yet.':'这个区间还没有可比的随机对照。')}</p></div>}</>
    :<p className="fwLead">{en?'No moves recorded for this period yet.':'这个区间还没有记录。'}</p>}
   </section>
   <section className="ovPanel" aria-label={en?'Evidence so far':'到目前为止的证据'}>
    <header><small>{en?'03 · Evidence so far':'03 · 到目前为止的证据'}</small></header>
    <div className="fwFacts">{(record?.facts??[]).filter(f=>f.id!=='locked-exam-limits').map(f=>{
     const tone=f.verdict==='FAIL'?'loss':f.verdict==='useful'?'go':'dim', chip=f.verdict==='FAIL'?(en?'Not passed':'没通过'):f.verdict==='useful'?(en?'Useful':'有用'):(en?'Reference':'仅参考');
     const meta=[en&&f.period?f.period.replace(' 至 ','–'):f.period,f.trades!=null?(en?`${f.trades} trades`:`${f.trades} 笔`):null,f.p!=null?`p ${f.p}`:null,f.average_R!=null?(en?`avg ${f.average_R}R`:`平均 ${f.average_R}R`):null,f.win_rate!=null?(en?`win ${Math.round(f.win_rate*100)}%`:`胜率 ${Math.round(f.win_rate*100)}%`):null].filter(Boolean).join(' · ');
     return <button key={f.id} type="button" className="fwFact" aria-expanded={open===f.id} onClick={()=>setOpen(open===f.id?null:f.id)}>
      <span className="fwFactTop"><b>{en?FACTS_EN[f.id]?.[0]??f.label:f.label}</b><em data-tone={tone}>{chip}</em></span><small>{meta}</small>
      {open===f.id&&<span className="fwFactNote">{en?FACTS_EN[f.id]?.[1]??f.note:f.note}</span>}</button>})}</div>
   </section>
  </div>
 </div>;
}
