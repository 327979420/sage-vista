'use client';
import {useEffect,useState} from 'react';
import {useLocale} from '../../../i18n/locale';

// Sectors, terminal view: every theme ETF on a pullback ladder (how far below its 60-day high,
// with the rule's 5–25% zone marked), grouped by state; theme strength appears when scored.
type Fund = {state?:string; close?:number; pullback_from_60d_high?:number|null; long_trend_qualified?:boolean; macd_bullish?:boolean; favorable_setup?:boolean; available?:boolean};
type DisplayTheme = {theme_id:string; name:string; reference_etf:string|null};
type Theme = {theme_id:string; name:string; state:string; strength_percentile:number|null; relative_20d:number|null; breadth_above_sma50:number|null};
export type Industry = {as_of:string; themes?:Theme[]; display_context?:{funds:Record<string,Fund>; themes:DisplayTheme[]}};

const ZH:Record<string,string> = {semiconductors:'半导体','software-applications':'软件应用',cybersecurity:'网络安全','cloud-computing':'云计算','robotics-automation':'机器人与自动化',uranium:'铀','copper-miners':'铜矿','clean-energy':'清洁能源',solar:'太阳能','oil-gas':'油气能源','critical-minerals':'关键矿产','battery-materials':'电池材料','defense-aerospace':'国防航空',infrastructure:'基建','grid-modernization':'电网升级',fintech:'金融科技','digital-assets':'数字资产',biotechnology:'生物科技','medical-devices':'医疗器械','ev-battery':'电动车电池','water-infrastructure':'水务基建'};
const STATES:[string,string,string,string][] = [['Rising Pullback At Support','回调到支撑','Pullback at support','var(--t-go)'],['Uptrend','上升趋势','Uptrend','#7cc4ff'],['Pullback Unconfirmed','回调未确认','Pullback unconfirmed','var(--t-wait)'],['Weak Or Unconfirmed','偏弱','Weak','#5c6670']];
const THEME_STATES:Record<string,[string,string]> = {Leadership:['领涨','Leading'],'Pullback Watch':['回调观察','Pullback watch'],Recovery:['恢复中','Recovering'],Neutral:['中性','Neutral']};
const MAX=0.75;

export default function SectorTerminal({data}:{data:Industry}) {
 const {locale}=useLocale(), en=locale==='en';
 const [sel,setSel]=useState<string|null>(null);
 const [ready,setReady]=useState(false);
 useEffect(()=>{const t=setTimeout(()=>setReady(true),150);return()=>clearTimeout(t)},[]);
 const funds=data.display_context?.funds??{}, scored=new Map((data.themes??[]).filter(t=>t.state!=='Unavailable').map(t=>[t.theme_id,t]));
 const rows=(data.display_context?.themes??[]).filter(t=>t.reference_etf&&funds[t.reference_etf]?.available!==false&&funds[t.reference_etf]?.state).map(t=>({...t,etf:t.reference_etf!,fund:funds[t.reference_etf!],score:scored.get(t.theme_id)}));
 if(!rows.length)return null;
 const name=(r:{theme_id:string;name:string})=>en?r.name:ZH[r.theme_id]??r.name;
 const count=(s:string)=>rows.filter(r=>r.fund.state===s).length;
 const x=rows.find(r=>r.etf===sel)??rows.find(r=>r.fund.favorable_setup)??rows[0];
 const P=(v:number)=>Math.min(v,MAX)/MAX*100;
 const lane=(s?:string)=>Math.max(0,STATES.findIndex(([k])=>k===s));
 const strength=[...scored.values()].filter(t=>t.strength_percentile!==null).sort((a,b)=>b.strength_percentile!-a.strength_percentile!);
 return <div className="ovRoot">
  <section className="ovHead"><div>
   <small>{en?`Market · Sectors · ${data.as_of}`:`市场 · 行业 · ${data.as_of}`}</small>
   <h1>{en?`${count(STATES[0][0])} themes have pulled back to support, ${count('Uptrend')} are in an uptrend.`:`${count(STATES[0][0])} 个主题回调到支撑，${count('Uptrend')} 个在上升趋势。`}</h1>
   <p>{en?'Each dot is a theme’s reference ETF, placed by how far it sits below its 60-day high. The rule looks for a long uptrend with a 5–25% pullback near a moving average.':'每个点是一个主题的参考 ETF，按离 60 日高点跌了多少排开。规则要找的是：长期上升趋势里，回调 5%–25%、靠近均线。'}</p>
  </div></section>
  <div className="scStates">{STATES.map(([k,zh,enL,c])=><div key={k} style={{borderTopColor:c}}><b style={{color:c}}>{count(k)}</b><span>{en?enL:zh}</span></div>)}</div>
  <div className="ovGrid scGrid">
   <section className="ovPanel" aria-label={en?'Pullback ladder':'回调梯子'}>
    <header><small>{en?'Pullback from the 60-day high · point at a dot':'离 60 日高点回调多少 · 指向任意一点'}</small></header>
    <div className="scLadder">
     <span className="scZone" style={{left:`${P(0.05)}%`,width:`${P(0.25)-P(0.05)}%`}}><em>{en?'rule zone 5–25%':'规则区间 5–25%'}</em></span>
     {STATES.map(([k,zh,enL],i)=><span key={k} className="scLane" style={{top:`${12+i*24}%`}}><em>{en?enL:zh}</em></span>)}
     {[...rows].sort((a,b)=>(a.fund.pullback_from_60d_high??0)-(b.fund.pullback_from_60d_high??0)).map((r,i)=>{const v=r.fund.pullback_from_60d_high??0,st=STATES[lane(r.fund.state)];return <button key={r.etf} type="button" className="scDot" data-flip={i%2||undefined} data-on={r.etf===x.etf||undefined} data-fav={r.fund.favorable_setup||undefined} aria-label={`${r.etf} ${(v*100).toFixed(1)}%`} onMouseEnter={()=>setSel(r.etf)} onFocus={()=>setSel(r.etf)} onClick={()=>setSel(r.etf)}
      style={{left:`${ready?P(v):0}%`,top:`${12+lane(r.fund.state)*24}%`,background:st[3]}}><span>{r.etf}</span></button>})}
    </div>
    <p className="mkFoot"><span>0%</span><span>{en?'below the 60-day high':'低于 60 日高点'}</span><span>{Math.round(MAX*100)}%+</span></p>
   </section>
   <section className="ovPanel" aria-label={en?'Theme detail':'主题详情'}>
    <header><small>{en?'Theme detail':'主题详情'}</small><span style={{color:STATES[lane(x.fund.state)][3]}} className="scState">{STATES[lane(x.fund.state)][en?2:1]}</span></header>
    <div className="sbDetailHead"><b>{x.etf}</b><span>{name(x)}</span></div>
    <div className="pfNums"><div><small>{en?'Below 60-day high':'离 60 日高点'}</small><b>{x.fund.pullback_from_60d_high==null?'—':`−${(x.fund.pullback_from_60d_high*100).toFixed(1)}%`}</b></div><div><small>{en?'Last close':'收盘'}</small><b>{x.fund.close==null?'—':`$${x.fund.close.toFixed(2)}`}</b></div></div>
    <ul className="scChecks"><li data-ok={!!x.fund.long_trend_qualified}>{x.fund.long_trend_qualified?'✓':'✕'} {en?'Long uptrend':'长期上升趋势'}</li><li data-ok={!!x.fund.macd_bullish}>{x.fund.macd_bullish?'✓':'✕'} {en?'MACD bullish':'MACD 偏多'}</li><li data-ok={!!x.fund.favorable_setup}>{x.fund.favorable_setup?'✓':'✕'} {en?'Pullback at support':'回调到支撑'}</li></ul>
    {x.score&&<p className="sbVerdict">{en?`Theme score: ${THEME_STATES[x.score.state]?.[1]??x.score.state}, stronger than ${Math.round(x.score.strength_percentile??0)}% of themes.`:`主题评分：${THEME_STATES[x.score.state]?.[0]??x.score.state}，强于 ${Math.round(x.score.strength_percentile??0)}% 的主题。`}</p>}
   </section>
  </div>
  {strength.length>0&&<section className="ovPanel" aria-label={en?'Theme strength':'主题强弱'}>
   <header><small>{en?'Theme strength · relative to SPY over 20 and 60 days':'主题强弱 · 相对 SPY 的 20 日和 60 日表现'}</small></header>
   <div className="scStrength">{strength.map(t=><button key={t.theme_id} type="button" onMouseEnter={()=>{const r=rows.find(y=>y.theme_id===t.theme_id);if(r)setSel(r.etf)}}><span>{en?t.name:ZH[t.theme_id]??t.name}</span><i><em style={{width:`${ready?t.strength_percentile:0}%`}}/></i><b>{THEME_STATES[t.state]?.[en?1:0]??t.state}</b></button>)}</div>
  </section>}
  <p className="mfListLabel">{en?'Every theme · holdings, candidates and sources':'全部主题 · 成分股、候选和来源'}</p>
 </div>;
}
