'use client';
import {useEffect,useState} from 'react';
import {useLocale} from '../../../i18n/locale';

// Fund flows, terminal view: which of 16 big ETFs took money in or out, from the issuers' own
// share counts (change in shares x NAV). Left: one bar per fund over the chosen window. Right:
// the daily total (or one fund, when you point at it); point at a day to read that day.
type Row = {date:string; value:number; funds:number} & Record<string,number|string>;
type Meta = {ticker:string; issuer:string; label:string; label_en:string; group:string};
export type FlowPanel = {status:string; frequency:string; observation_date:string|null; history?:Row[]; funds_meta?:Meta[]; missing?:string[]};
const GROUPS:[string,string,string][] = [['equity','股票','Stocks'],['style','风格','Style'],['bonds','债券','Bonds'],['dollar','美元','Dollar']];
const SPANS = [1,5,20];
const money = (v:number) => {const a=Math.abs(v), s=v>0?'+':v<0?'−':'';return a>=1?`${s}$${a.toFixed(2)}B`:`${s}$${Math.round(a*1000)}M`};

export default function FlowsPanel({panel}:{panel:FlowPanel|null}) {
 const {locale}=useLocale(), en=locale==='en';
 const [span,setSpan]=useState(0);
 const [day,setDay]=useState<number|null>(null);
 const [fund,setFund]=useState<string|null>(null);
 const [ready,setReady]=useState(false);
 useEffect(()=>{const t=setTimeout(()=>setReady(true),150);return()=>clearTimeout(t)},[]);
 const rows=panel?.history??[], meta=panel?.funds_meta??[];
 if(!panel||panel.status==='unavailable'||rows.length<2||!meta.length)return null;
 const shown=rows.slice(-40), end=day===null?rows.length-1:rows.length-shown.length+day, endRow=rows[end];
 const win=rows.slice(Math.max(0,end-SPANS[span]+1),end+1);
 const sums=meta.map(m=>{const vals=win.map(r=>r[m.ticker]).filter((v):v is number=>typeof v==='number');return {...m,total:vals.reduce((a,b)=>a+b,0),days:vals.length}});
 const covered=sums.filter(s=>s.days), total=covered.reduce((a,s)=>a+s.total,0);
 const max=Math.max(0.05,...covered.map(s=>Math.abs(s.total)));
 const top=[...covered].sort((a,b)=>b.total-a.total), inflow=top[0], outflow=top[top.length-1];
 const name=(m:Meta)=>en?m.label_en:m.label;
 const series=shown.map(r=>fund?(typeof r[fund]==='number'?r[fund] as number:null):r.value);
 const peak=Math.max(0.05,...series.map(v=>Math.abs(v??0)));
 const focus=fund?meta.find(m=>m.ticker===fund):null;
 const endVal=fund?(typeof endRow[fund]==='number'?endRow[fund] as number:null):endRow.value;
 const spanWord=en?['that day','5 sessions','20 sessions'][span]:['当天','近 5 个交易日','近 20 个交易日'][span];
 return <section className="ovPanel flPanel" aria-label={en?'Fund flows':'资金流'}>
  <header><small>{en?`Fund flows · 16 big ETFs · issuer share counts · to ${endRow.date}`:`资金流 · 16 只大型 ETF · 发行商份额数据 · 截至 ${endRow.date}`}</small>
   <span className="fwSpans">{(en?['1 day','5 days','20 days']:['1 日','5 日','20 日']).map((label,i)=><button key={label} type="button" aria-pressed={i===span} onClick={()=>setSpan(i)}>{label}</button>)}</span></header>
  <p className="flLead">{en
   ?<>Over {spanWord}, these funds took in <b data-tone={total>=0?'go':'loss'}>{money(total)}</b> net.{inflow&&inflow.total>0&&<> Most in: <b>{inflow.ticker}</b> {money(inflow.total)}.</>}{outflow&&outflow.total<0&&<> Most out: <b>{outflow.ticker}</b> {money(outflow.total)}.</>}</>
   :<>{spanWord}，这些基金合计净{total>=0?'流入':'流出'} <b data-tone={total>=0?'go':'loss'}>{money(total)}</b>。{inflow&&inflow.total>0&&<>流入最多：<b>{inflow.ticker}</b> {money(inflow.total)}。</>}{outflow&&outflow.total<0&&<>流出最多：<b>{outflow.ticker}</b> {money(outflow.total)}。</>}</>}</p>
  <div className="flBody">
   <div className="flBars" onMouseLeave={()=>setFund(null)}>{GROUPS.map(([g,zh,enL])=><div key={g}><small>{en?enL:zh}</small>
    {sums.filter(s=>s.group===g).map(s=><button key={s.ticker} type="button" className="flBar" aria-pressed={s.ticker===fund} onMouseEnter={()=>setFund(s.ticker)} onFocus={()=>setFund(s.ticker)} onClick={()=>setFund(fund===s.ticker?null:s.ticker)}
     aria-label={`${s.ticker} ${s.days?money(s.total):(en?'no data yet':'暂无数据')}`}>
     <b>{s.ticker}</b><span className="flName">{name(s)}</span>
     <span className="flTrack"><i/>{s.days>0&&<em data-tone={s.total>=0?'go':'loss'} style={{width:`${ready?Math.abs(s.total)/max*50:0}%`,[s.total>=0?'left':'right']:'50%'}}/>}</span>
     <span className="flNum" data-tone={s.days?(s.total>=0?'go':'loss'):undefined}>{s.days?money(s.total):(en?'building':'积累中')}{s.days>0&&s.days<win.length&&<small> {s.days}/{win.length}{en?'d':'天'}</small>}</span>
    </button>)}</div>)}</div>
   <div className="flDaily">
    <p className="mkRead"><b>{focus?`${focus.ticker} · ${name(focus)}`:(en?'All 16 funds, daily total':'16 只合计，每日')}</b>
     <span>{endRow.date} <em data-tone={endVal===null?undefined:endVal>=0?'go':'loss'}>{endVal===null?'—':money(endVal)}</em></span>
     {!fund&&<span>{en?`${endRow.funds} of 16 reported`:`${endRow.funds}/16 只有数据`}</span>}</p>
    <div className="flChart" onMouseLeave={()=>setDay(null)}>
     <i className="flZero"/>
     {series.map((v,i)=><button key={shown[i].date} type="button" aria-label={`${shown[i].date} ${v===null?'—':money(v)}`} aria-pressed={i===(day??shown.length-1)} onMouseEnter={()=>setDay(i)} onFocus={()=>setDay(i)} onClick={()=>setDay(i)}>
      {v!==null&&<em data-tone={v>=0?'go':'loss'} style={{height:`${ready?Math.abs(v)/peak*50:0}%`,[v>=0?'bottom':'top']:'50%'}}/>}</button>)}
    </div>
    <p className="mkFoot"><span>{shown[0].date.slice(5)}</span><span>{en?'point at a day · point at a fund on the left':'指向某一天 · 指向左边某只基金'}</span><span>{shown[shown.length-1].date.slice(5)}</span></p>
   </div>
  </div>
  <p className="flNote">{en
   ?'Flow = change in shares outstanding × NAV, from iShares, State Street SPDR and Invesco. Issuers often book creations a day late, so this is registered creations and redemptions, not intraday buying. iShares funds have no history file, so their figures build up from the first collected day.'
   :'流量 = 份额变化 × 当天净值，数据来自 iShares、State Street SPDR、Invesco 官网。发行商常常晚一天登记申购赎回，所以这是“已登记的申赎”，不是当天盘中的买卖。iShares 没有历史文件，它的数字从开始采集那天起逐日积累。'}{panel?.missing?.length?(en?` Not read this time: ${panel.missing.join(', ')}.`:` 本次没读到：${panel.missing.join('、')}。`):''}</p>
 </section>;
}
