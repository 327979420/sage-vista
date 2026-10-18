'use client';
import {useEffect,useState,type ReactNode} from 'react';
import {Localized} from '../i18n/locale';
import {fetchEvidence} from './data';
export function useEvidence<T>(url:string|null,valid:(v:unknown)=>v is T) {
 const [state,setState]=useState<{url:string;data:T|null}|null>(null);
 useEffect(()=>{
  if(!url)return;
  const control=new AbortController();let active=true;
  const timeout=setTimeout(()=>control.abort(),10000);
  void fetchEvidence(url,valid,control.signal).then(data=>{clearTimeout(timeout);if(active)setState({url,data})});
  return()=>{active=false;clearTimeout(timeout);control.abort()};
 },[url,valid]);
 return {loading:!!url&&state?.url!==url,data:state?.url===url?state.data:null};
}
export function EvidenceHeader({forward=false,children}:{forward?:boolean;children?:ReactNode}) {
 return <Localized><header className="rtSubHero"><div><p>FROZEN RULE · 3w-1.9</p><h1>{forward?'前向记录':'信号凭证'}</h1><strong>{forward?'从新信号开始，记录发生了什么。':'每个信号一张凭证：为什么触发、为什么挂单、后来怎样。'}</strong></div><aside>{children??'每周五收盘后检查'}</aside></header><nav className="candidateFrameChips svEvidenceNav" aria-label="3W 研究"><a href="/signals" aria-current={!forward?'page':undefined}>信号凭证</a><a href="/forward" aria-current={forward?'page':undefined}>前向记录</a></nav></Localized>;
}
const labels:Record<string,string>={waiting:'等待成交',filled:'已成交',open:'已成交',closed:'已平仓',cancelled:'已取消',skipped:'不挂单',unverified:'未核验',unavailable:'暂无数据'};
export function Status({status}:{status:string}) {return <Localized><span className={`svEvidenceChip ${status==='unverified'?'isWarning':''}`}>{labels[status]??'暂无数据'}</span></Localized>}
export const num=(value:unknown,d=2)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(d):'—';
export const pct=(value:number|null|undefined)=>value===null||value===undefined?'—':`${num(value)}%`;
export const rText=(value:number|null|undefined)=>value===null||value===undefined?'—':`${num(value)}R`;
