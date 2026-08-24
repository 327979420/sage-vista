"use client";
import { ReactNode, useEffect, useState } from "react";

export type Frame={macd:string;macd_score:number;macd_histogram:number;zero_zone:string;bars_since_cross:number|null;rsi:string;rsi_score:number;rsi_value:number|null};
export type Item={symbol:string;price:number;macd_score:number;rsi_score:number;macd_resonance:number;rsi_resonance:number;chain_score:number;chain_reason:string;macd_gate_reason:string;combined_score:number;rsi_divergence_frames:string[];price_structure:{confirmed:boolean;score:number;label:string;evidence:string[]};volume:{label:string;score:number;ratio:number|null;near_bottom:boolean;direction:string};frames:Record<string,Frame>};
export type Report={as_of:string;universe:{cached:number;eligible:number};combined_top10:Item[];macd_top10:Item[];rsi_top10:Item[];volume_top10:Item[]};
export const periods=["日线","周线","月线"];
export const modules=[
 ["总览","/zh/watch/resonance"],["双指标确认","/zh/watch/resonance/confluence"],["MACD","/zh/watch/resonance/macd"],["RSI","/zh/watch/resonance/rsi"],["成交量","/zh/watch/resonance/volume"],
] as const;
export function useTracker(){const [data,setData]=useState<Report|null>(null);useEffect(()=>{fetch("/resonance-tracker.json").then(x=>x.json()).then(setData)},[]);return data}
export function TrackerShell({active,title,subtitle,children}:{active:string;title:string;subtitle:string;children:ReactNode}){
 const data=useTracker();
 return <main className="rtPage"><header className="rtSubHero"><div><a href="/zh/watch">← 盯盘助手</a><p>INDICATOR TRACKER</p><h1>{title}</h1><strong>{subtitle}</strong></div>{data&&<aside><small>数据截至</small><b>{data.as_of}</b><span>扫描 {data.universe.eligible} 只</span></aside>}</header><nav className="rtModuleNav">{modules.map(([label,url])=><a key={url} className={active===label?"active":""} href={url}>{label}</a>)}</nav>{!data&&active!=="需求取舍"?<div className="rtLoading">正在载入最新数据…</div>:children}</main>
}
function PeriodCell({frame,kind}:{frame:Frame;kind:"macd"|"rsi"}){const hot=kind==="macd"?frame.macd_score>=2:frame.rsi_score>=2;return <div className={`rtPeriod ${hot?"isHot":""}`}><small>{kind==="macd"?frame.zero_zone:"RSI"}</small><b>{kind==="macd"?frame.macd:frame.rsi}</b><span>{kind==="macd"?`柱 ${frame.macd_histogram}`:frame.rsi_value??"—"}</span></div>}
export function SignalBoard({items,kind,combined}:{items:Item[];kind:"macd"|"rsi";combined:Set<string>}){return <div className="rtBoard"><div className="rtBoardHead"><span>标的</span>{periods.map(x=><span key={x}>{x}</span>)}<span>评分</span></div>{items.map((item,index)=><article className="rtSignalRow" key={item.symbol}><div className="rtTicker"><i>{String(index+1).padStart(2,"0")}</i><div><b>{item.symbol}</b><small>${item.price}</small></div>{combined.has(item.symbol)&&<mark>MACD ＋ RSI</mark>}{kind==="macd"&&<mark className={item.price_structure.confirmed?"structureOn":"structureOff"}>{item.price_structure.label}</mark>}</div>{periods.map(period=><PeriodCell key={period} frame={item.frames[period]} kind={kind}/>)}<div className="rtScore"><b>{kind==="macd"?item.macd_score:item.rsi_score}</b><small>{kind==="macd"?`链条 +${item.chain_score}`:`${item.rsi_resonance}/3 周期`}</small></div>{kind==="macd"&&<p className="rtReason">{item.chain_reason}<span>{item.price_structure.evidence.join(" · ")||"暂无价格结构确认"}</span></p>}</article>)}</div>}
