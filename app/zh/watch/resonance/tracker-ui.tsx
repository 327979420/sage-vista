"use client";
import {Localized} from '../../../i18n/locale';
import {ReactNode,useEffect,useState} from "react";

type UpdateStatus={
 status:"up_to_date"|"stale"|"failed";
 source_latest_complete_date:string;
 data_dates_match:boolean;
 last_successful_update_at:string;
};

export const modules=[
 ["大盘","/zh/watch/market"],
 ["行业","/zh/watch/industry-radar"],
 ["多因子机会","/zh/watch/resonance/rare-opportunities"],
 ["我最喜欢形态","/zh/watch/resonance/favorite-pattern"],
 ["回测","/zh/backtest"],
] as const;

const modulePaths=[
 "M3 17V7m6 10V3m6 14v-6m6 6V5",
 "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
 "M4 5h16M4 12h10M4 19h6m6-4 3 3 4-6",
 "m3 16 4-7 5 8 5-12 4 5",
 "M4 4v16h17M8 15l4-5 4 2 5-7",
];

function useUpdateStatus(){
 const [status,setStatus]=useState<UpdateStatus|null>(null);
 useEffect(()=>{fetch("/update-status.json",{cache:"no-store"}).then(x=>x.ok?x.json():null).then(setStatus).catch(()=>setStatus(null))},[]);
 return status;
}

export function TrackerShell({active,title,subtitle,description,children,overview=false}:{active:string;title:string;subtitle:string;description?:string;children:ReactNode;overview?:boolean}){
 const status=useUpdateStatus();
 const synced=status?.status==="up_to_date"&&status.data_dates_match;
 return <Localized><main className={`rtPage ${overview?"rtOverviewPage":""}`}>
  <nav className="rtModuleNav" aria-label="主要功能">{modules.map(([label,url],index)=><a key={url} className={active===label?"active":""} aria-current={active===label?"page":undefined} href={url}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={modulePaths[index]}/></svg><span>{label}</span></a>)}</nav>
  {!overview&&<header className="rtSubHero"><div><a href="/zh/watch/resonance/about">Sage Vista · 功能介绍</a><p>DAILY TRADING RESEARCH</p><h1>{title}</h1><strong>{subtitle}</strong>{description&&<p className="rtHeroDescription">{description}</p>}</div>{status&&<aside className={synced?"isCurrent":"needsCheck"}><small>最新完整美股收盘</small><b>{status.source_latest_complete_date}</b><span className="rtSyncState">{synced?"✓ 核心数据已同步":"! 更新状态待核验"}</span><span>多因子、形态、行业使用同一收盘日；大盘覆盖单独核验</span>{status.last_successful_update_at&&<time dateTime={status.last_successful_update_at}>成功更新 {new Date(status.last_successful_update_at).toLocaleString("zh-CN",{timeZone:"Australia/Melbourne",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false})}（墨尔本）</time>}</aside>}</header>}
  {!status&&active!=="功能介绍"&&<div className="rtLoading">行情状态载入中，页面功能可以正常使用。</div>}
  {children}
 </main></Localized>;
}
