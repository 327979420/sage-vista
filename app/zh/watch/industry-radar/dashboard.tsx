"use client";
import {useState} from 'react';
import {TrackerShell} from '../resonance/tracker-ui';
import {useDailyData} from '../market/daily-data';
import {names,type Context,type Theme} from './context';
const PATHS=['/update-status.json','/industry-radar.json','/cr056-ranking.json'] as const;
const states:Record<string,string>={'Rising Pullback At Support':'回调至支撑',Uptrend:'趋势向上','Pullback Unconfirmed':'回调待确认','Weak Or Unconfirmed':'偏弱 / 待确认',Unavailable:'等待更新'};
const order:Record<string,number>={'Rising Pullback At Support':0,Uptrend:1,'Pullback Unconfirmed':2,'Weak Or Unconfirmed':3};
const FILTERS=[['all','全部'],['strong','趋势向上'],['pullback','回调中'],['weak','偏弱 / 待确认']] as const;
export function IndustryView({context,targetDate,candidates=[],candidateDate}:{context:Context|null;targetDate:string;candidates?:string[];candidateDate?:string}){
 const [filter,setFilter]=useState('all'),[search,setSearch]=useState('');
 const current=!!context&&!!targetDate&&context.as_of===targetDate;
 const fund=(theme:Theme)=>theme.reference_etf?context?.funds[theme.reference_etf]:null;
 const usable=(t:Theme)=>{const f=fund(t);return current&&!t.manual&&f?.available&&f.as_of===targetDate&&f.latest_bar===targetDate};
 const ready=(context?.themes??[]).filter(usable).sort((a,b)=>(order[fund(a)!.state]??9)-(order[fund(b)!.state]??9));
 const pending=(context?.themes??[]).filter(t=>!usable(t));
 const matches=(t:Theme)=>(`${names[t.theme_id]??t.name} ${t.reference_etf??''}`).toLowerCase().includes(search.trim().toLowerCase());
 const strong=(t:Theme)=>fund(t)!.state==='Uptrend';
 const pullback=(t:Theme)=>['Rising Pullback At Support','Pullback Unconfirmed'].includes(fund(t)!.state);
 const visible=ready.filter(t=>matches(t)&&(filter==='all'||filter==='strong'&&strong(t)||filter==='pullback'&&pullback(t)||filter==='weak'&&fund(t)!.state==='Weak Or Unconfirmed'));
 const card=(t:Theme,valid:boolean)=>{
  const f=fund(t),name=names[t.theme_id]??t.name;
  const links=valid&&candidateDate===targetDate&&t.membership_as_of&&t.membership_as_of<=targetDate?t.members.filter(s=>candidates.includes(s)):[];
  const distance=valid&&Number.isFinite(f?.pullback_from_60d_high)?f!.pullback_from_60d_high! *100:null;
  return <article className="mvpIndustryCard" key={t.theme_id}>
   <header><div><span className="mvpQuiet">{t.reference_etf??'主题观察'}</span><h3>{name}</h3></div><span className="mvpState" data-state={valid?f?.state:'unavailable'}>{valid?states[f!.state]??'待确认':t.manual?'暂无对应ETF':'等待更新'}</span></header>
   <div className="mvpIndustryMetric"><span>回到60日高点需涨</span><strong>{distance===null?'—':`${distance.toFixed(1)}%`}</strong></div>
   <div className="mvpDistance" aria-hidden="true"><i style={{width:`${distance===null?0:Math.min(100,Math.max(0,distance))}%`}}/></div>
   <details className="mvpIndustryDetail"><summary>相关候选 <span>{links.length} 只</span></summary>{links.length?<div className="mvpCandidateLinks">{links.map(code=><a key={code} href={`/zh/watch/resonance/rare-opportunities?symbol=${encodeURIComponent(code)}`}>{code} ↗</a>)}</div>:<p>{candidateDate!==targetDate?'候选榜等待同日更新':'当前没有匹配的合格候选'}</p>}<p>高点按过去60个交易日的最高收盘价比较。</p><p>关联依据持仓快照 {t.membership_as_of&&t.membership_as_of<=targetDate?t.membership_as_of:'待补'}，不代表实时持仓。</p></details>
  </article>
 };
 return <div className="marketDashboard mvpDashboard">
  <section className="mvpIntro"><div><p className="marketEyebrow">SECTOR OVERVIEW</p><h2>哪些行业向上，哪些正在回调？</h2><p>用行业 ETF 看方向，展开卡片看相关候选。</p></div><span className="mvpDate">收盘日 {targetDate||'待更新'}</span></section>
  {!current&&<p className="marketError" role="status">行业数据等待更新{context?`，目前保存至 ${context.as_of}`:''}。</p>}
  <section className="mvpKpis mvpIndustryTotals" aria-label="行业状态概览"><article className="mvpKpi"><header>已更新</header><strong>{ready.length}<small> / {context?.themes.length??'—'}</small></strong><footer>行业与主题</footer></article><article className="mvpKpi"><header>趋势向上</header><strong data-direction="up">{ready.filter(strong).length}</strong><footer>保持上行</footer></article><article className="mvpKpi"><header>回调中</header><strong>{ready.filter(pullback).length}</strong><footer>观察是否企稳</footer></article><article className="mvpKpi"><header>偏弱 / 待确认</header><strong>{ready.filter(t=>fund(t)!.state==='Weak Or Unconfirmed').length}</strong><footer>方向仍需确认</footer></article></section>
  <div className="mvpToolbar"><div className="mvpTabs" role="group" aria-label="行业状态筛选">{FILTERS.map(([key,label])=><button key={key} onClick={()=>setFilter(key)} aria-pressed={filter===key}>{label}</button>)}</div><label className="mvpSearch"><span>搜索</span><input aria-label="搜索行业或ETF" placeholder="行业 / ETF，如半导体、SOXX" value={search} onChange={e=>setSearch(e.target.value)}/></label></div>
  <div className="mvpIndustryGrid">{visible.map(t=>card(t,true))}</div>
  {!visible.length&&<p className="mvpEmpty">没有符合当前筛选的行业。</p>}
  {pending.length>0&&<details className="mvpPending" open={search.trim()?true:undefined}><summary>待补数据的主题 <span>{pending.length}</span></summary><div className="mvpIndustryGrid">{pending.filter(matches).map(t=>card(t,false))}</div></details>}
  <p className="mvpFooter">每天更新一次并复用 · ETF 反映行业方向，不等于买入信号</p>
 </div>
}
export default function IndustryRadar(){
 const {reports,loading,refresh}=useDailyData(PATHS);
 const targetDate=(reports[PATHS[0]] as {source_latest_complete_date?:string}|null)?.source_latest_complete_date??'';
 const industry=reports[PATHS[1]] as {as_of:string;future_data_used:boolean;display_context:Context}|null;
 const rank=reports[PATHS[2]] as {as_of:string;ranked_symbols:string[]}|null;
 return <TrackerShell active="行业" title="行业" subtitle="行业方向与相关机会。" overview>
  <div className="mvpPageTitle"><div><h1>行业</h1><p>每日行业速览</p></div><button className="mvpRefresh" onClick={refresh}>↻ 刷新</button></div>
  {loading?<p className="marketLoading" role="status">正在读取行业快照…</p>:<IndustryView context={industry&&!industry.future_data_used&&industry.as_of===targetDate?industry.display_context:null} targetDate={targetDate} candidates={rank?.ranked_symbols??[]} candidateDate={rank?.as_of}/>}
 </TrackerShell>
}
