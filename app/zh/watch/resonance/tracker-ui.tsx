"use client";
import {ReactNode,useEffect,useState} from "react";

type UpdateStatus={
 status:"up_to_date"|"stale"|"failed";
 source_latest_complete_date:string;
 data_dates_match:boolean;
 last_successful_update_at:string;
};

export const modules=[
 ["今日研究总览","/"],
 ["多因子机会","/zh/watch/resonance/rare-opportunities"],
 ["我最喜欢形态","/zh/watch/resonance/favorite-pattern"],
 ["行业与大盘","/zh/watch/industry-radar"],
] as const;

function useUpdateStatus(){
 const [status,setStatus]=useState<UpdateStatus|null>(null);
 useEffect(()=>{fetch("/update-status.json",{cache:"no-store"}).then(x=>x.ok?x.json():null).then(setStatus).catch(()=>setStatus(null))},[]);
 return status;
}

export function TrackerShell({active,title,subtitle,children,overview=false}:{active:string;title:string;subtitle:string;children:ReactNode;overview?:boolean}){
 const status=useUpdateStatus();
 const synced=status?.status==="up_to_date"&&status.data_dates_match;
 return <main className={`rtPage ${overview?"rtOverviewPage":""}`}>
  {!overview&&<header className="rtSubHero"><div><a href="/zh/watch/resonance/about">Sage Vista · 功能介绍</a><p>DAILY TRADING RESEARCH</p><h1>{title}</h1><strong>{subtitle}</strong></div>{status&&<aside className={synced?"isCurrent":"needsCheck"}><small>最新完整美股收盘</small><b>{status.source_latest_complete_date}</b><span className="rtSyncState">{synced?"✓ 核心数据已同步":"! 更新状态待核验"}</span><span>今日、多因子、形态、行业大盘使用同一收盘日</span>{status.last_successful_update_at&&<time dateTime={status.last_successful_update_at}>成功更新 {new Date(status.last_successful_update_at).toLocaleString("zh-CN",{timeZone:"Australia/Melbourne",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false})}（墨尔本）</time>}</aside>}</header>}
  <nav className="rtModuleNav" aria-label="主要功能">{modules.map(([label,url])=><a key={url} className={active===label?"active":""} href={url}>{label}</a>)}</nav>
  {!status&&active!=="功能介绍"&&<div className="rtLoading">行情状态载入中，页面功能可以正常使用。</div>}
  {children}
 </main>;
}
