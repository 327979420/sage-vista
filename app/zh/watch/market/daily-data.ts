"use client";
import {useCallback,useEffect,useState} from 'react';

// Avoid AbortSignal.any/timeout: older Safari versions do not implement them.
export async function fetchDailyAsset(path:string, parent:AbortSignal, timeoutMs=15000){
 const request=new AbortController();
 const abort=()=>request.abort();
 if(parent.aborted)abort();
 else parent.addEventListener('abort',abort,{once:true});
 const timer=setTimeout(abort,timeoutMs);
 try{
  const response=await fetch(path,{cache:'no-store',signal:request.signal});
  if(!response.ok)throw new Error('daily_asset_unavailable');
  return await response.json();
 }finally{
  clearTimeout(timer);
  parent.removeEventListener('abort',abort);
 }
}

// Pages read published daily assets. They never fetch prices or scan securities.
export function useDailyData(paths:readonly string[]){
 const [reports,setReports]=useState<Record<string,unknown>>({});
 const [loading,setLoading]=useState(true),[attempt,setAttempt]=useState(0);
 const refresh=useCallback(()=>setAttempt(n=>n+1),[]);
 useEffect(()=>{
  let active=true;let busy=false;const controller=new AbortController();
  const load=async()=>{
   if(busy)return;busy=true;
   const results=await Promise.allSettled(paths.map(path=>fetchDailyAsset(path,controller.signal)));
   if(active){setReports(Object.fromEntries(paths.map((p,i)=>[p,results[i].status==='fulfilled'?results[i].value:null])));setLoading(false)}
   busy=false;
  };
  void load();const timer=setInterval(()=>{if(document.visibilityState==='visible')void load()},300000);
  const visible=()=>{if(document.visibilityState==='visible')void load()};document.addEventListener('visibilitychange',visible);
  return()=>{active=false;controller.abort();clearInterval(timer);document.removeEventListener('visibilitychange',visible)};
 },[paths,attempt]);
 return {reports,loading,refresh};
}
