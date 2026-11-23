'use client';
import {useEffect,useState} from 'react';
import {useLocale} from '../i18n/locale';
import type {SignalRow} from '../app/signal-rows';

// Signal board: one card per signal with its price ladder (stop, limit, 3R target, latest price),
// and a check trace that lights each gate in order with its real value.
type Filter = 'all'|'gate'|'rule'|string;
const fmt = (v:number) => v.toFixed(2);
const pctOf = (v:number) => `${(v*100).toFixed(1)}%`;

function verdictOf(r:SignalRow, en:boolean) {
 if(r.status==='open')return en?'Order filled; the position is open.':'已成交，持仓中。';
 if(r.status==='closed')return en?'Trade closed; it counts toward the record.':'已平仓，计入成绩。';
 if(r.status==='waiting')return en?'Limit order placed; waiting for the price to come back.':'限价单已挂，等价格回落成交。';
 const fails:string[]=[];
 if(r.veto)fails.push(en?'the monthly MACD vetoed it':'月线 MACD 否决');
 if(r.rrOk===false)fails.push(en?`reward/risk is only ${r.rr?.toFixed(2)}, under 1.5`:`盈亏比只有 ${r.rr?.toFixed(2)}，不到 1.5`);
 if(r.ruleOk&&!r.gateOk)return en?'Passed the rule, but the market light was amber: under half the pool was above its 200-day line that week.':'规则都过了，但市场灯是黄的：那周股票池站上 200 日线的不到一半。';
 if(r.gateOk===false)fails.push(en?`the market light was amber (${r.breadth===null?'—':pctOf(r.breadth)})`:`市场灯是黄的（${r.breadth===null?'—':pctOf(r.breadth)}）`);
 const text=(r.gateOk?(en?'The market light was green, but ':'市场灯是绿的，但'):'')+fails.join(en?'; ':'，')+(en?', so no order.':'，所以不做。');
 return text.charAt(0).toUpperCase()+text.slice(1);
}
function chipOf(r:SignalRow, en:boolean):[string,string] {
 if(r.status==='open')return [en?'Open':'持仓','go'];
 if(r.status==='closed')return [en?'Closed':'已平仓','go'];
 if(r.status==='waiting')return [en?'Order waiting':'等成交','wait'];
 return r.ruleOk?[en?'Stopped by market':'大盘拦下','wait']:[en?'Failed the rule':'规则不过','dim'];
}

// Distance to pass for the two checks with a line (bullet-graph style, after Stephen Few: the value
// as a dot, the pass mark as a thin line). Reward/risk is drawn on 0–3, breadth on 30–70%.
const RR_LINE = 1.5, BREADTH_LINE = 0.5;
type Gap = {label:string; value:string; ok:boolean|null; pos:number|null; note:string; miss:number|null};
function gaps(r:SignalRow, en:boolean):Gap[] {
 const rrShort=r.rr!==null&&r.rrOk===false?RR_LINE-r.rr:null;
 const bShort=r.breadth!==null&&r.breadth<=BREADTH_LINE?(BREADTH_LINE-r.breadth)*100:null;
 const spyFail=r.spyOk===false;
 return [
  {label:en?'Reward/risk':'盈亏比', value:r.rr===null?'—':r.rr.toFixed(2), ok:r.rrOk, pos:r.rr===null?null:Math.min(1,Math.max(0,r.rr/3)),
   note:r.rrOk?(en?'passed':'通过'):rrShort===null?'—':(en?`short by ${rrShort.toFixed(2)}`:`差 ${rrShort.toFixed(2)}`), miss:rrShort===null?null:rrShort/RR_LINE},
  {label:en?'Market':'大盘', value:r.breadth===null?'—':pctOf(r.breadth), ok:r.gateOk, pos:r.breadth===null?null:Math.min(1,Math.max(0,(r.breadth-.3)/.4)),
   note:r.gateOk?(en?'passed':'通过'):spyFail?(en?'SPY under its 200-day':'SPY 在 200 日线下'):bShort===null?'—':(en?`short by ${bShort.toFixed(1)} pts`:`差 ${bShort.toFixed(1)} 个点`),
   miss:spyFail?Infinity:bShort===null?null:bShort/(BREADTH_LINE*100)},
 ];
}
// A closest call: skipped, with every failed check within 10% of its line (no veto, shape intact).
// The score is the summed shortfall, so the smallest miss comes first.
export function closeness(r:SignalRow):number|null {
 if(r.status!=='skipped'||r.veto||r.shapePassed!==r.shapeTotal)return null;
 const misses=gaps(r,true).filter(g=>g.ok===false).map(g=>g.miss);
 if(!misses.length||misses.some(m=>m===null||m>=.1))return null;
 return misses.reduce<number>((sum,m)=>sum+(m as number),0);
}
function Bullet({g}:{g:Gap}) {
 return <span className="sbBullet" data-ok={g.ok===null?undefined:String(g.ok)}>
  <span className="sbBulletName">{g.label}</span>
  <span className="sbBulletBar" aria-hidden="true"><i className="sbBulletPass"/><i className="sbBulletLine"/>{g.pos!==null&&<i className="sbBulletDot" style={{left:`${g.pos*100}%`}}/>}</span>
  <span className="sbBulletVal"><em>{g.value}</em> · {g.note}</span>
 </span>;
}

function Ladder({r,ready,en}:{r:SignalRow;ready:boolean;en:boolean}) {
 const now=r.close??r.limit, lo=Math.min(r.stop,now)*0.96, hi=Math.max(r.target,now)*1.03, p=(v:number)=>(v-lo)/(hi-lo)*100;
 const at=ready?p(now):p(r.limit);
 const ticks:[number,string,string][]=[[r.stop,en?'Stop':'止损','loss'],[r.limit,en?'Limit':'挂单','wait'],[r.target,'3R','go']];
 return <div className="sbLadder" aria-hidden="true">
  <span className="sbZone" data-tone="loss" style={{left:`${p(r.stop)}%`,width:`${p(r.limit)-p(r.stop)}%`}}/>
  <span className="sbZone" data-tone="go" style={{left:`${p(r.limit)}%`,width:`${p(r.target)-p(r.limit)}%`}}/>
  {ticks.map(([v,label,tone])=><span key={label}><i className="sbTick" data-tone={tone} style={{left:`${p(v)}%`}}/><em className="sbTickLabel" data-tone={tone} style={{left:`${p(v)}%`}}>{label}</em></span>)}
  {r.close!==null&&<><i className="sbNow" style={{left:`${at}%`}}/><em className="sbNowLabel" style={{left:`${at}%`}}>{en?'Now':'现价'} {fmt(r.close)}</em></>}
 </div>;
}

function Trace({r,en,run}:{r:SignalRow;en:boolean;run:number}) {
 const steps:[string,boolean|null,string,string][]=[
  [en?'Shape and basics':'形态和基本条件',r.shapeTotal?r.shapePassed===r.shapeTotal:null,en?`${r.shapePassed}/${r.shapeTotal} passed`:`${r.shapePassed}/${r.shapeTotal} 项通过`,en?'Weekly triangle shape, bottoms, pullback, MACD cross and liquidity match the locked rule.':'周线三角的形状、底部、回调、金叉和成交量都符合锁定的规则。'],
  [en?'Monthly MACD, no veto':'月线 MACD 不否决',r.veto===null?null:!r.veto,r.veto?(en?'veto':'否决'):(en?'no veto':'没否决'),en?'Skip names whose monthly trend is turning down.':'月线趋势正在转坏的，不做。'],
  [en?'Reward/risk ≥ 1.5':'盈亏比 ≥ 1.5',r.rrOk,r.rr===null?'—':r.rr.toFixed(2),en?'What it can make must be at least 1.5× what it can lose.':'能赚的至少要是可能亏的 1.5 倍。'],
  [en?'Market light':'市场灯',r.gateOk,r.breadth===null?'—':pctOf(r.breadth),en?'SPY above its 200-day line, and over half the pool above theirs in the signal week.':'SPY 在 200 日线上方，且信号那周股票池过半站上 200 日线。'],
 ];
 return <ol className="sbTrace" key={run} aria-label={en?'Checks':'检查过程'}>{steps.map(([label,ok,value,plain],i)=><li key={label} style={{animationDelay:`${i*0.35}s`}} data-ok={ok===null?undefined:String(ok)}>
  <span>{ok===null?'·':ok?'✓':'✕'}</span><div><p><b>{label}</b><em>{value}</em></p><small>{plain}</small></div>
 </li>)}</ol>;
}

export default function SignalBoard({rows,selected,onSelect}:{rows:SignalRow[];selected:string|null;onSelect:(id:string)=>void}) {
 const {locale}=useLocale(), en=locale==='en';
 const [filter,setFilter]=useState<Filter>('all');
 const [run,setRun]=useState(0);
 const [ready,setReady]=useState(false);
 useEffect(()=>{const id=setTimeout(()=>setReady(true),150);return()=>clearTimeout(id)},[]);
 const weeks=[...new Set(rows.map(r=>r.week))].sort().reverse();
 const sorted=[...rows].sort((a,b)=>b.week.localeCompare(a.week)||a.symbol.localeCompare(b.symbol));
 const near=rows.map(r=>[r,closeness(r)] as const).filter((p):p is readonly [SignalRow,number]=>p[1]!==null).sort((a,b)=>a[1]-b[1]||a[0].symbol.localeCompare(b[0].symbol)).map(([r])=>r);
 const nearIds=new Set(near.map(r=>r.id));
 const keep=(r:SignalRow)=>filter==='all'||(filter==='near'&&nearIds.has(r.id))||(filter==='gate'&&r.status==='skipped'&&r.ruleOk)||(filter==='rule'&&!r.ruleOk)||r.week===filter;
 const chips:[Filter,string,number][]=[['all',en?'All':'全部',rows.length],...weeks.map(w=>[w,en?`Week of ${w.slice(5)}`:`${w.slice(5)} 周`,rows.filter(r=>r.week===w).length] as [Filter,string,number]),
  ...(near.length?[['near',en?'Closest calls':'差一点',near.length] as [Filter,string,number]]:[]),
  ['gate',en?'Stopped by market':'大盘拦下',rows.filter(r=>r.status==='skipped'&&r.ruleOk).length],['rule',en?'Failed the rule':'规则不过',rows.filter(r=>!r.ruleOk).length]];
 const x=rows.find(r=>r.id===selected)??sorted[0];
 const pick=(id:string)=>{onSelect(id);setRun(v=>v+1)};
 const gap=x.close===null?null:(x.close/x.limit-1)*100;
 const facts:[string,string,string,string,string][]=[
  [en?'Limit':'挂单',fmt(x.limit),en?'2% under the signal close':'信号收盘价下方 2%','wait',en?'The buy price. It only fills if the price comes back to here.':'想买的价格，价格回落到这里才成交。'],
  [en?'Stop':'止损',fmt(x.stop),en?'1% under the last bottom':'最后一个底下方 1%','loss',en?'Sell here to admit the trade is wrong; this loss is 1R.':'跌到这里就认错卖出，亏的就是 1R。'],
  [en?'Target':'目标',fmt(x.target),'3R','go',en?'Take profit at 3 times the risk.':'赚到 3 倍风险（3R）就卖出。'],
  [en?'Breadth':'广度',x.breadth===null?'—':pctOf(x.breadth),en?'signal week, needs 50%':'信号那周，门槛 50%',x.gateOk?'go':'wait',en?'Share of the pool above its 200-day line. Over half means most stocks are in uptrends.':'股票池里站上 200 日线的股票占比，过半说明大多数股票在上涨趋势里。'],
 ];
 return <section className="sbBoard" aria-label={en?'Signal board':'信号看板'}>
  {near.length>0&&<section className="sbNear" aria-label={en?'Closest calls':'差一点就过'}>
   <header><small>{en?'Closest calls':'差一点就过'}</small><small>{en?`${near.length} missed by under 10%`:`${near.length} 个差不到 10%`}</small></header>
   <div className="sbNearList">{near.slice(0,3).map(r=><button key={r.id} type="button" className="sbNearCard" aria-pressed={r.id===x.id} onClick={()=>pick(r.id)}>
    <span className="sbNearTop"><b>{r.symbol}</b><small>{en?`week of ${r.week.slice(5)}`:`${r.week.slice(5)} 周`}</small></span>
    {gaps(r,en).map(g=><Bullet key={g.label} g={g}/>)}
   </button>)}</div>
   <p className="sbLocked">{en?'Locked rule: near misses are not traded. ':'规则锁定，差一点也不做。'}<a href="/forward">{en?'What they did next →':'后来怎样 →'}</a></p>
  </section>}
  <div className="sbChips" role="group" aria-label={en?'Filter':'筛选'}>{chips.map(([id,label,n])=><button key={id} type="button" aria-pressed={filter===id} onClick={()=>setFilter(id)}>{label} <i>{n}</i></button>)}</div>
  <div className="sbLayout">
   <div className="sbCards">{sorted.filter(keep).map(r=>{const [chip,tone]=chipOf(r,en);return <button key={r.id} type="button" className="sbCard" aria-pressed={r.id===x.id} onClick={()=>pick(r.id)}>
    <div className="sbCardTop"><div><b>{r.symbol}</b><small>{en?`week of ${r.week.slice(5)}`:`${r.week.slice(5)} 周`}</small></div><span data-tone={tone}>{chip}</span></div>
    <Ladder r={r} ready={ready} en={en}/>
    <span className="sbCardFoot">{gaps(r,en).map(g=><Bullet key={g.label} g={g}/>)}</span>
   </button>})}</div>
   <aside className="sbDetail" aria-label={en?'Signal detail':'信号详情'}>
    <small>{en?'Signal detail':'信号详情'}</small>
    <div className="sbDetailHead"><b>{x.symbol}</b><span>{en?`week of ${x.week.slice(5)}`:`${x.week.slice(5)} 周`}</span></div>
    <p className="sbVerdict">{verdictOf(x,en)}</p>
    <Trace r={x} en={en} run={run}/>
    <dl className="sbFacts">{facts.map(([k,v,sub,tone,tip])=><div key={k}><dt><button type="button" className="sbHint" aria-label={`${k}: ${tip}`} data-tip={tip}>{k}</button></dt><dd data-tone={tone}>{v}</dd><small>{sub}</small></div>)}</dl>
    {x.close!==null&&gap!==null&&<p className="sbNowLine">{en?`Last price ${fmt(x.close)} (${x.priceAsOf}), ${Math.abs(gap).toFixed(1)}% ${gap>=0?'above':'below'} the limit.`:`现价 ${fmt(x.close)}（${x.priceAsOf}），比挂单价${gap>=0?'高':'低'} ${Math.abs(gap).toFixed(1)}%。`}{x.close<=x.stop?(en?' Already below the stop.':'已经跌破止损位。'):''}</p>}
   </aside>
  </div>
 </section>;
}

export function SignalsHead({rows}:{rows:SignalRow[]|null}) {
 const {locale}=useLocale(), en=locale==='en';
 const orders=rows?.filter(r=>r.status!=='skipped').length??0;
 return <section className="ovHead sbHead"><div>
  <h1>{rows?(en?`${rows.length} signals, ${orders} orders.`:`${rows.length} 个信号，${orders} 个下单。`):(en?'Signal evidence':'信号凭证')}</h1>
  <p>{en?'Pick a card to see its checks.':'点一张卡看它的检查。'}</p>
 </div></section>;
}
