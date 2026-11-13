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
 if(r.rrOk===false)fails.push(en?`R:R is only ${r.rr?.toFixed(2)}, under 1.5`:`盈亏比只有 ${r.rr?.toFixed(2)}，不到 1.5`);
 if(r.ruleOk&&!r.gateOk)return en?'Passed the shape and the rules, stopped at the last gate: under half the pool was above its 200-day line that week.':'形态和规则都过了，只卡在最后一关：那周股票池里站上 200 日线的股票不到一半。';
 if(r.gateOk===false)fails.push(en?`the gate was closed (${r.breadth===null?'—':pctOf(r.breadth)})`:`闸门没开（${r.breadth===null?'—':pctOf(r.breadth)}）`);
 return (r.gateOk?(en?'The gate was open, but ':'闸门是开的，但'):'')+fails.join(en?'; ':'，')+(en?', so no order.':'，所以不做。');
}
function chipOf(r:SignalRow, en:boolean):[string,string] {
 if(r.status==='open')return [en?'Open':'持仓','go'];
 if(r.status==='closed')return [en?'Closed':'已平仓','go'];
 if(r.status==='waiting')return [en?'Order waiting':'等成交','wait'];
 return r.ruleOk?[en?'Gate blocked':'闸门挡住','wait']:[en?'Rule says no':'规则不做','dim'];
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
  [en?'Shape and basics':'形态和基本条件',r.shapeTotal?r.shapePassed===r.shapeTotal:null,en?`${r.shapePassed}/${r.shapeTotal} passed`:`${r.shapePassed}/${r.shapeTotal} 项通过`,en?'Weekly triangle shape, bottoms, pullback, MACD cross and liquidity match the frozen rule.':'周线三角的形状、底部、回调、金叉和成交量都符合冻结规则。'],
  [en?'Monthly MACD, no veto':'月线 MACD 不否决',r.veto===null?null:!r.veto,r.veto?(en?'veto':'否决'):(en?'no veto':'没否决'),en?'Skip names whose monthly trend is turning down.':'月线趋势正在转坏的，不做。'],
  ['R:R ≥ 1.5',r.rrOk,r.rr===null?'—':r.rr.toFixed(2),en?'What it can make must be at least 1.5× what it can lose.':'能赚的至少要是可能亏的 1.5 倍。'],
  [en?'Market gate':'市场闸门',r.gateOk,r.breadth===null?'—':pctOf(r.breadth),en?'SPY above its 200-day line, and over half the pool above theirs in the signal week.':'SPY 在 200 日线上方，且信号那周股票池过半站上 200 日线。'],
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
 const keep=(r:SignalRow)=>filter==='all'||(filter==='gate'&&r.status==='skipped'&&r.ruleOk)||(filter==='rule'&&!r.ruleOk)||r.week===filter;
 const chips:[Filter,string,number][]=[['all',en?'All':'全部',rows.length],...weeks.map(w=>[w,en?`Week of ${w.slice(5)}`:`${w.slice(5)} 周`,rows.filter(r=>r.week===w).length] as [Filter,string,number]),
  ['gate',en?'Gate blocked':'闸门挡住',rows.filter(r=>r.status==='skipped'&&r.ruleOk).length],['rule',en?'Rule says no':'规则不做',rows.filter(r=>!r.ruleOk).length]];
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
  <div className="sbChips" role="group" aria-label={en?'Filter':'筛选'}>{chips.map(([id,label,n])=><button key={id} type="button" aria-pressed={filter===id} onClick={()=>setFilter(id)}>{label} <i>{n}</i></button>)}</div>
  <div className="sbLayout">
   <div className="sbCards">{sorted.filter(keep).map(r=>{const [chip,tone]=chipOf(r,en);return <button key={r.id} type="button" className="sbCard" aria-pressed={r.id===x.id} onClick={()=>pick(r.id)}>
    <div className="sbCardTop"><div><b>{r.symbol}</b><small>{en?`week of ${r.week.slice(5)}`:`${r.week.slice(5)} 周`} · {r.pool==='main'?(en?'main pool':'主股票池'):r.pool}</small></div><span data-tone={tone}>{chip}</span></div>
    <Ladder r={r} ready={ready} en={en}/>
    <div className="sbCardFoot"><span>R:R <em data-tone={r.rrOk===false?'loss':undefined}>{r.rr===null?'—':r.rr.toFixed(2)}</em></span><span>{en?'Breadth':'广度'} <em data-tone={r.gateOk?'go':'wait'}>{r.breadth===null?'—':pctOf(r.breadth)}</em></span></div>
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
  <small>{en?'3W · Signals · frozen rule 3w-1.9':'3W · 信号 · 冻结规则 3w-1.9'}</small>
  <h1>{rows?(en?`${rows.length} signals, ${orders} orders.`:`${rows.length} 个信号，${orders} 个下单。`):(en?'Signal evidence':'信号凭证')}</h1>
  <p>{en?'Each card is one signal’s plan: where to buy, where to stop, where to take profit, and its latest price. Pick a card to see which checks it passed and where it stopped.':'每张卡是一个信号的计划：在哪挂单、在哪止损、目标在哪，以及它现在的价格。点一张卡，右边会一步步亮出它过了哪些关、卡在哪一关。'}</p>
 </div></section>;
}
