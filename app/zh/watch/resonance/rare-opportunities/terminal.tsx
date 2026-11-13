'use client';
import {useEffect,useState} from 'react';
import {useLocale} from '../../../../i18n/locale';

// Multi-factor, terminal view: the top five as cards, every ranked stock on a score map
// (score against return since nomination), and how 1,500 stocks narrowed to the list.
type Review = {symbol:string; rank:number|null; price:number|null; status:string; total:number|null; watch_return:number|null; origin_date?:string|null;
 frames?:Record<string,number|undefined>; reason_codes?:string[]; watch_entries?:{path:string}[]};
type Ranking = {as_of:string; reviews:Review[]; selected_symbols:string[]};
const PATHS:Record<string,[string,string,string]> = {bottom_macd:['底部 MACD 金叉','Bottom MACD cross','#7cc4ff'],support_reversal:['支撑反转','Support reversal','var(--t-wait)'],three_push_breakout:['三推突破','Three-push breakout','#c9a7ff']};
const REASONS:Record<string,[string,string]> = {monthly_not_confirmed:['月线没确认','Monthly not confirmed'],structure_broken:['结构破坏','Structure broken'],daily_tradability_not_met:['日线成交不够','Daily liquidity too low'],near_observed_history_high:['接近历史高点','Near its high'],monthly_high_zone:['月线高位','Monthly high zone'],no_available_background:['没有可用背景','No usable background'],completed_months_below_61:['月线历史不足','Too little monthly history'],no_confirmed_reversal_entry:['没有确认的反转入场','No confirmed reversal'],weekly_not_confirmed:['周线没确认','Weekly not confirmed']};
const FRAMES:[string,string,string][] = [['monthly_completed','月','M'],['weekly_completed','周','W'],['daily','日','D']];
const pathOf = (r:Review) => r.watch_entries?.[0]?.path ?? 'bottom_macd';
const pct = (v:number) => `${v>0?'+':v<0?'−':''}${Math.abs(v*100).toFixed(1)}%`;

export default function MultiFactorTerminal() {
 const {locale}=useLocale(), en=locale==='en';
 const [data,setData]=useState<Ranking|null>(null);
 const [sel,setSel]=useState<string|null>(null);
 const [ready,setReady]=useState(false);
 useEffect(()=>{let active=true;fetch('/cr056-ranking.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(d=>{if(active&&d&&Array.isArray(d.reviews))setData(d);setTimeout(()=>active&&setReady(true),150)}).catch(()=>{});return()=>{active=false}},[]);
 if(!data)return null;
 const ranked=data.reviews.filter(r=>r.rank!==null&&r.total!==null).sort((a,b)=>a.rank!-b.rank!);
 const top=ranked.slice(0,5), x=ranked.find(r=>r.symbol===sel)??top[0];
 const reasons=Object.entries(data.reviews.reduce<Record<string,number>>((acc,r)=>{const c=r.reason_codes?.[0];if(c&&REASONS[c])acc[c]=(acc[c]??0)+1;return acc},{})).sort((a,b)=>b[1]-a[1]).slice(0,6);
 const maxReason=reasons[0]?.[1]??1;
 const scores=ranked.map(r=>r.total!), rets=ranked.map(r=>r.watch_return??0);
 const sLo=Math.floor(Math.min(...scores)/5)*5, sHi=Math.ceil(Math.max(...scores)/5)*5;
 const rAbs=Math.max(0.1,...rets.map(Math.abs)), X=(v:number)=>(v-sLo)/(sHi-sLo||1)*100, Y=(v:number)=>50-v/rAbs*46;
 const name=(p:string)=>PATHS[p]?.[en?1:0]??p;
 return <div className="ovRoot">
  <section className="ovHead"><div>
   <small>{en?`Candidates · Multi-factor · ${data.as_of}`:`候选 · 多因子 · ${data.as_of}`}</small>
   <h2>{en?`${ranked.length} stocks made the list. Start with these five.`:`${ranked.length} 只进入排名，先看这 5 只。`}</h2>
   <p>{en?'Each stock is scored on monthly, weekly and daily charts (bigger charts count more). The score ranks what to research first; it is not a win rate.':'每只股票按月线、周线、日线打分（周期越大权重越高）。分数决定先研究哪只，不是胜率。'}</p>
  </div></section>
  <div className="mfTop">{top.map((r,i)=><button key={r.symbol} type="button" className="mfCard" aria-pressed={r.symbol===x.symbol} onClick={()=>setSel(r.symbol)} onMouseEnter={()=>setSel(r.symbol)} style={{transitionDelay:`${i*80}ms`}} data-ready={ready||undefined}>
   <span className="mfRank">#{r.rank}</span><b>{r.symbol}</b><span className="mfScore">{r.total!.toFixed(1)}</span>
   <span className="mfFrames">{FRAMES.map(([k,zh,enL])=><span key={k}><small>{en?enL:zh}</small><i><em style={{width:`${ready?Math.round((r.frames?.[k]??0)*100):0}%`}}/></i></span>)}</span>
   <span className="mfFoot"><em style={{color:PATHS[pathOf(r)]?.[2]}}>{name(pathOf(r))}</em><em data-tone={(r.watch_return??0)>=0?'go':'loss'}>{r.watch_return===null?'—':pct(r.watch_return)}</em></span>
  </button>)}</div>
  <div className="ovGrid mfGrid">
   <section className="ovPanel" aria-label={en?'Score map':'分数地图'}>
    <header><small>{en?'Score map · score vs return since it joined the list · point at a dot':'分数地图 · 分数 vs 入榜以来涨跌 · 指向任意一点'}</small></header>
    <div className="mfMap">
     <span className="mfAxisY" style={{top:`${Y(0)}%`}}><em>0%</em></span>
     {ranked.map(r=><button key={r.symbol} type="button" className="mfDot" data-top={r.rank!<=5||undefined} data-on={r.symbol===x.symbol||undefined} aria-label={`${r.symbol} ${r.total!.toFixed(1)}`} onMouseEnter={()=>setSel(r.symbol)} onFocus={()=>setSel(r.symbol)} onClick={()=>setSel(r.symbol)}
      style={{left:`${X(r.total!)}%`,top:`${ready?Y(r.watch_return??0):50}%`,background:PATHS[pathOf(r)]?.[2]}}>{r.rank!<=5&&<span>{r.symbol}</span>}</button>)}
    </div>
    <p className="mkFoot"><span>{en?`score ${sLo}`:`分数 ${sLo}`}</span><span className="mfLegend">{Object.entries(PATHS).map(([k,[zh,enL,c]])=><span key={k}><i style={{background:c}}/>{en?enL:zh}</span>)}</span><span>{sHi}</span></p>
    <div className="mfPick"><b>#{x.rank} {x.symbol}</b><span>{x.price!==null?`$${x.price.toFixed(2)}`:''}</span><span>{en?'score':'分数'} {x.total!.toFixed(1)}</span><span>{name(pathOf(x))}</span>
     <strong data-tone={(x.watch_return??0)>=0?'go':'loss'}>{x.watch_return===null?'—':pct(x.watch_return)} <small>{en?`since ${x.origin_date??'—'}`:`自 ${x.origin_date??'—'} 入榜`}</small></strong></div>
   </section>
   <section className="ovPanel" aria-label={en?'How the list was narrowed':'怎么筛出来的'}>
    <header><small>{en?'How 1,500 stocks became a list':'1,500 只怎么变成一张榜'}</small></header>
    <div className="mfNarrow"><div><b>{data.reviews.length}</b><span>{en?'reviewed':'只复评'}</span></div><i>›</i><div><b>{ranked.length}</b><span>{en?'ranked':'进入排名'}</span></div><i>›</i><div><b>{data.selected_symbols.length}</b><span>{en?'to look at first':'先看'}</span></div></div>
    <p className="fwLead">{en?'Most common reasons a stock was left out:':'被排除最常见的原因：'}</p>
    <ul className="mfReasons">{reasons.map(([code,n])=><li key={code}><span>{REASONS[code][en?1:0]}</span><i><em style={{width:`${ready?n/maxReason*100:0}%`}}/></i><b>{n}</b></li>)}</ul>
   </section>
  </div>
  <p className="mfListLabel">{en?'The full list · search any stock, filter and open its details':'完整榜单 · 搜索任意股票、筛选、展开详情'}</p>
 </div>;
}
