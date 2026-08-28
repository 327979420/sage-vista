"use client";
import Link from "next/link";
import {ReactNode,useEffect,useState} from "react";

type TrackerOpportunity={symbol:string;price:number};
export type Report={
 as_of:string;
 universe:{eligible:number};
 macd_buy_top10:TrackerOpportunity[];
};
type UpdateStatus={
 status:"up_to_date"|"stale"|"failed";
 source_latest_complete_date:string;
 data_dates_match:boolean;
 last_successful_update_at:string;
};

export const modules=[
 ["今日研究总览","/"],
 ["多因子机会","/zh/watch/resonance/rare-opportunities"],
 ["行业与大盘","/zh/watch/industry-radar"],
 ["历史与实验","/zh/watch/resonance/research"],
] as const;

export function useTracker(){
 const [data,setData]=useState<Report|null>(null);
 useEffect(()=>{fetch("/resonance-tracker.json",{cache:"no-store"}).then(x=>x.json()).then(setData)},[]);
 return data;
}

function useUpdateStatus(){
 const [status,setStatus]=useState<UpdateStatus|null>(null);
 useEffect(()=>{fetch("/update-status.json",{cache:"no-store"}).then(x=>x.ok?x.json():null).then(setStatus).catch(()=>setStatus(null))},[]);
 return status;
}

export function TrackerShell({active,title,subtitle,children,overview=false}:{active:string;title:string;subtitle:string;children:ReactNode;overview?:boolean}){
 const data=useTracker(),status=useUpdateStatus();
 const synced=!!data&&status?.status==="up_to_date"&&status.data_dates_match&&status.source_latest_complete_date===data.as_of;
 return <main className={`rtPage ${overview?"rtOverviewPage":""}`}>
  {!overview&&<header className="rtSubHero"><div><Link href="/zh/watch/resonance/about">Sage Vista · 功能介绍</Link><p>QUANTITATIVE RESEARCH WORKSPACE</p><h1>{title}</h1><strong>{subtitle}</strong></div>{data&&<aside className={synced?"isCurrent":"needsCheck"}><small>最新完整美股收盘</small><b>{data.as_of}</b><span className="rtSyncState">{synced?"✓ 已与数据源同步":"! 更新状态待核验"}</span><span>Tracker / 数据审计同日 · 扫描 {data.universe.eligible} 只</span>{status?.last_successful_update_at&&<time dateTime={status.last_successful_update_at}>成功更新 {new Date(status.last_successful_update_at).toLocaleString("zh-CN",{timeZone:"Australia/Melbourne",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false})}（墨尔本）</time>}</aside>}</header>}
  <nav className="rtModuleNav" aria-label="主要功能">{modules.map(([label,url])=><Link key={url} className={active===label?"active":""} href={url}>{label}</Link>)}</nav>
  {!data&&active!=="功能介绍"?<div className="rtLoading">正在载入最新数据…</div>:children}
 </main>;
}
