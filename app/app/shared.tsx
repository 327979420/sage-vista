'use client';
import {Localized} from '../i18n/locale';
import {useEffect,useState,type ReactNode} from 'react';
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
export function Header({current,children}:{current:'today'|'portfolio';children?:ReactNode}) {
 return <Localized><header className="rtSubHero"><div><a href="/zh/watch/resonance/about">Sage Vista · 功能介绍</a><p>DAILY TRADING RESEARCH</p><h1>{s[current]}</h1><strong>{current==='today'?s.todayIntro:s.portfolioIntro}</strong></div><aside>{children??<Missing loading/>}</aside></header></Localized>;
}
export function Missing({loading=false}:{loading?:boolean}) {return <Localized><div className="cockpitEmpty" role="status"><strong>{loading?s.loading:s.missing}</strong>{!loading&&<p>{s.missingDetail}</p>}</div></Localized>}
export function Source({rule}:{rule:string}) {return <Localized><small className="svAppSource">{s.source}：{rule.split(" · ").flatMap((part,index)=>index?[" · ",part]:[part])}</small></Localized>}
export function DataDate({date}:{date:string}) {return <Localized><p className="svAppMeta">{s.date}：<time>{date}</time></p></Localized>}
export function percent(value:number|null|undefined, decimals=1) {return typeof value==='number'&&Number.isFinite(value)?`${value.toFixed(decimals)}%`:s.unavailable}
export function risk(value:number|null|undefined) {return typeof value==='number'&&Number.isFinite(value)?`${value.toFixed(1)}R`:s.unavailable}
