'use client';
import {useEffect,useState} from 'react';
import {useLocale} from '../../i18n/locale';
import type {Portfolio,Signals} from '../data';

// My portfolio, terminal view: the 50/50 split, a switchboard of the ten core sleeves (each one a
// gauge of its distance from the 200-day line, moving from month-end to today), and the 3W slots.
const NAMES:Record<string,[string,string]> = {XLB:['原材料','Materials'],XLE:['能源','Energy'],XLF:['金融','Financials'],XLI:['工业','Industrials'],XLK:['科技','Technology'],XLP:['必需消费','Staples'],XLU:['公用事业','Utilities'],XLV:['医疗','Health care'],XLY:['可选消费','Discretionary'],SPY:['标普 500','S&P 500']};
const LO=-10, HI=22;
const at = (v:number) => (Math.max(LO,Math.min(HI,v))-LO)/(HI-LO)*100;
// One ring segment between two angles (degrees, 0 = 12 o'clock) of the account donut.
const ring = (a0:number,a1:number,R=54,r0=40) => {const p=(a:number,r:number)=>`${(60+r*Math.sin(a*Math.PI/180)).toFixed(2)} ${(60-r*Math.cos(a*Math.PI/180)).toFixed(2)}`;return `M${p(a0,R)}A${R} ${R} 0 ${a1-a0>180?1:0} 1 ${p(a1,R)}L${p(a1,r0)}A${r0} ${r0} 0 ${a1-a0>180?1:0} 0 ${p(a0,r0)}Z`};
const signed = (v:number) => `${v>0?'+':v<0?'−':''}${Math.abs(v).toFixed(2)}%`;
// Last weekday of the month as the month-end rebalance day (exchange holidays aside).
function monthEnd(asOf:string) {const d=new Date(asOf+'T00:00:00Z'),e=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0));while([0,6].includes(e.getUTCDay()))e.setUTCDate(e.getUTCDate()-1);return e.toISOString().slice(0,10)}

export default function PortfolioTerminal({data,signals}:{data:Portfolio;signals:Signals|null}) {
 const {locale}=useLocale(), en=locale==='en';
 const [sel,setSel]=useState<string|null>(null);
 const [ready,setReady]=useState(false);
 useEffect(()=>{const t=setTimeout(()=>setReady(true),200);return()=>clearTimeout(t)},[]);
 const rows=[...data.sleeves].sort((a,b)=>(b.today.distance_pct??-99)-(a.today.distance_pct??-99));
 const inMarket=rows.filter(r=>r.today.hold&&r.today.hold!=='SHY').length, safe=rows.length-inMarket;
 const nearest=rows.filter(r=>r.today.distance_pct!==null).sort((a,b)=>Math.abs(a.today.distance_pct!)-Math.abs(b.today.distance_pct!))[0];
 const x=rows.find(r=>r.symbol===sel)??nearest;
 const open=signals?.signals.filter(s=>s.status==='open').length??0;
 const end=monthEnd(data.as_of);
 const name=(sym:string)=>NAMES[sym]?.[en?1:0]??sym;
 const verdict=(d:number|null,hold:string|null)=>d===null?(en?'No price':'没有价格'):d>=0?(en?`Above its 200-day line: if the month ended today it would hold ${hold==='SHY'?'the fund (switch in)':'the fund'}.`:`在 200 日线上方：如果今天就是月底，会持有这只基金${hold==='SHY'?'（从 SHY 换回来）':''}。`):(en?`Below its 200-day line: if the month ended today it would sit in SHY${hold!=='SHY'?' (switch out)':''}.`:`在 200 日线下方：如果今天就是月底，会放在 SHY 避险${hold!=='SHY'?'（要换出去）':''}。`);
 return <div className="ovRoot">
  <section className="ovHead"><div>
   <small>{en?'3W · My portfolio · paper account':'3W · 我的组合 · 模拟账户'}</small>
   <h1>{en?`${inMarket} sectors in the market, ${safe} parked in SHY.`:`${inMarket} 个行业在场，${safe} 个放在 SHY 避险。`}</h1>
   <p>{en?'Half the account follows the sector trend basket and is only rebalanced at month-end; the other half waits for 3W signals.':'一半资金跟行业趋势篮子，只在月底调仓；另一半等 3W 信号下单。'}</p>
  </div><div className="ovNext"><small>{en?`Next rebalance · close of ${end.slice(5)}`:`下次调仓 · ${end.slice(5)} 收盘`}</small><b className="ovCount">{Math.max(0,Math.round((Date.parse(end)-Date.parse(data.as_of))/86400000))}<small>{en?' days':' 天'}</small></b></div></section>
  <div className="ovGrid pfGrid">
   <section className="ovPanel" aria-label={en?'Account split':'资金分配'}>
    <header><small>{en?'01 · Account split':'01 · 资金分配'}</small></header>
    <div className="pfSplit">
     <svg viewBox="0 0 120 120" aria-hidden="true">{rows.map((r,i)=><path key={r.symbol} className="pfSlice" data-on={r.symbol===x?.symbol||undefined} data-safe={r.today.hold==='SHY'||undefined} d={ring(i*18+0.8,i*18+17.2)} onMouseEnter={()=>setSel(r.symbol)}/>)}<path className="pfSat" d={ring(180.8,359.2)}/></svg>
     <div><p><b>{en?'Core 50%':'核心 50%'}</b> {en?'10 sleeves × 5%':'10 个行业各 5%'}</p><p><i data-safe/> {en?`${safe} in SHY`:`${safe} 个在 SHY`}</p><p><b className="pfSatLabel">{en?'Satellite 50%':'卫星 50%'}</b> {en?`${open} of 10 slots used`:`10 个位置用了 ${open} 个`}</p>
      <div className="pfSlots">{Array.from({length:10},(_,i)=><i key={i} data-used={i<open||undefined}/>)}</div></div>
    </div>
   </section>
   <section className="ovPanel pfDetail" aria-label={en?'Sleeve detail':'行业详情'}>
    <header><small>{en?'02 · Closest to switching':'02 · 最接近换仓'}</small>{x&&<span data-tone={x.today.hold==='SHY'?'wait':'go'}>{x.today.hold}</span>}</header>
    {x&&<><div className="sbDetailHead"><b>{x.symbol}</b><span>{name(x.symbol)}</span></div>
     <div className="pfNums"><div><small>{en?'Today':'今天'}</small><b data-tone={(x.today.distance_pct??0)>=0?'go':'loss'}>{x.today.distance_pct===null?'—':signed(x.today.distance_pct)}</b><span>{x.today.price_as_of}</span></div>
      <div><small>{en?'Last month-end':'上个月底'}</small><b>{x.month_end.distance_pct===null?'—':signed(x.month_end.distance_pct)}</b><span>{x.month_end.price_as_of}</span></div></div>
     <p className="sbVerdict">{verdict(x.today.distance_pct,x.today.hold)}</p></>}
   </section>
  </div>
  <section className="ovPanel" aria-label={en?'Sector switchboard':'行业开关板'}>
   <header><small>{en?'03 · Switchboard · distance from the 200-day line · dot moves from month-end to today':'03 · 开关板 · 离 200 日线多远 · 圆点从上个月底走到今天'}</small></header>
   <div className="pfBoard">{rows.map(r=>{const d=r.today.distance_pct, m=r.month_end.distance_pct;return <button key={r.symbol} type="button" className="pfRow" aria-pressed={r.symbol===x?.symbol} onMouseEnter={()=>setSel(r.symbol)} onFocus={()=>setSel(r.symbol)} onClick={()=>setSel(r.symbol)}>
    <span className="pfSym"><b>{r.symbol}</b><small>{name(r.symbol)}</small></span>
    <span className="pfGauge"><i className="pfZero" style={{left:`${at(0)}%`}}/>{m!==null&&<i className="pfGhost" style={{left:`${at(m)}%`}}/>}{d!==null&&<><i className="pfBar" data-up={d>=0||undefined} style={{left:`${Math.min(at(0),at(ready?d:0))}%`,width:`${Math.abs(at(ready?d:0)-at(0))}%`}}/><i className="pfDot" data-up={d>=0||undefined} style={{left:`${at(ready?d:(m??0))}%`}}/></>}</span>
    <span className="pfVal" data-tone={(d??0)>=0?'go':'loss'}>{d===null?'—':signed(d)}</span>
    <span className="pfHold" data-safe={r.today.hold==='SHY'||undefined}>{r.today.hold??'—'}{r.would_switch?(en?' · switch':' · 将换'):''}</span>
   </button>})}</div>
   <p className="mkFoot"><span>{LO}%</span><span>{en?'200-day line':'200 日线'}</span><span>+{HI}%</span></p>
  </section>
 </div>;
}
