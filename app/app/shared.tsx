'use client';
import {useEffect,useState} from 'react';
import {fetchReport,type Reports} from './data';
import {strings as s} from './strings';
export function useReport<K extends keyof Reports>(kind:K) {
  const [state,setState]=useState<{loading:boolean;data:Reports[K]|null}>({loading:true,data:null});
  useEffect(()=>{
    const controller=new AbortController();
    let active=true;
    const timeout=setTimeout(()=>controller.abort(),10000);
    void fetchReport(kind,controller.signal).then(data=>{if(active)setState({loading:false,data});clearTimeout(timeout)});
    return ()=>{active=false;clearTimeout(timeout);controller.abort()};
  },[kind]);
  return state;
}
export function Header({current}:{current:'today'|'portfolio'}) {
  return <header className="svAppHeader"><span>{s.brand}</span><nav aria-label={s.nav}>
    <a href="/app" aria-current={current==='today'?'page':undefined}>{s.today}</a>
    <button disabled>{s.opportunities}<small>{s.soon}</small></button>
    <a href="/app/portfolio" aria-current={current==='portfolio'?'page':undefined}>{s.portfolio}</a>
    <button disabled>{s.record}<small>{s.soon}</small></button><button disabled>{s.learn}<small>{s.soon}</small></button>
  </nav></header>;
}
export function Missing({loading=false}:{loading?:boolean}) {return <div className="svAppEmpty" role="status"><strong>{loading?s.loading:s.missing}</strong>{!loading&&<p>{s.missingDetail}</p>}</div>}
export function Source({rule}:{rule:string}) {return <small className="svAppSource">{s.source}：{rule}</small>}
export function DataDate({date}:{date:string}) {return <p className="svAppMeta">{s.date}：<time>{date}</time></p>}
export function percent(value:number|null|undefined, decimals=1) {return typeof value==='number'&&Number.isFinite(value)?`${value.toFixed(decimals)}%`:s.unavailable}
export function risk(value:number|null|undefined) {return typeof value==='number'&&Number.isFinite(value)?`${value.toFixed(1)}R`:s.unavailable}
