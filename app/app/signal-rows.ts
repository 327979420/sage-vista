'use client';
import {useEffect,useState} from 'react';
import {fetchEvidence,validIndex,validTicket,type Ticket} from '../evidence/data';

// One row per 3W signal for the terminal views: the plan and price from signals.json,
// and what each gate check decided from that signal's ticket. All files are already public.
export type SignalRow = {
 id:string; symbol:string; week:string; pool:string; status:string;
 limit:number; stop:number; target:number; close:number|null; priceAsOf:string|null;
 breadth:number|null; spyOk:boolean|null;
 shapePassed:number; shapeTotal:number; rr:number|null; rrOk:boolean|null; veto:boolean|null; gateOk:boolean|null;
 ruleOk:boolean; filled:boolean;
};
type SignalsFile = {signals:{id:string;symbol:string;week:string;dataset:string;status:string;
 market:{breadth:number|null;ok:boolean|null;spy_over_200d:boolean|null}|null;
 order:{limit:number;stop:number;target:number}|null; quote:{close:number|null;price_as_of:string|null}|null}[]};

const RULE_CHECKS = new Set(['monthly_macd_veto','plan_reward_to_risk','spy_over_200d','breadth_over_half']);
const finite = (v:unknown):v is number => typeof v==='number'&&Number.isFinite(v);
function validSignals(v:unknown):v is SignalsFile {
 if(!v||typeof v!=='object'||!Array.isArray((v as SignalsFile).signals))return false;
 return (v as SignalsFile).signals.every(s=>s&&typeof s.id==='string'&&typeof s.symbol==='string'&&typeof s.week==='string'&&s.order!==null&&typeof s.order==='object'&&['limit','stop','target'].every(k=>finite((s.order as Record<string,unknown>)[k])));
}
const poolName = (dataset:string) => dataset.startsWith('universe') ? 'main' : dataset.replace(/-\d{4}-v\d+$/, '');

export function toRow(s:SignalsFile['signals'][number], t:Ticket|null):SignalRow {
 const check=(id:string)=>t?.checks.find(c=>c.id===id);
 const shape=t?t.checks.filter(c=>!RULE_CHECKS.has(c.id)):[];
 const rrCheck=check('plan_reward_to_risk'), rrValue=(rrCheck?.value as {rr?:unknown}|undefined)?.rr;
 const veto=check('monthly_macd_veto'), gate=check('breadth_over_half'), spy=check('spy_over_200d');
 const rrOk=rrCheck?rrCheck.pass:null, vetoed=veto?!veto.pass:null;
 const gateOk=gate&&spy?gate.pass&&spy.pass:(s.market?.ok??null);
 return {id:s.id, symbol:s.symbol, week:s.week, pool:poolName(s.dataset), status:t?.outcome.status??s.status,
  limit:s.order!.limit, stop:s.order!.stop, target:s.order!.target, close:s.quote?.close??null, priceAsOf:s.quote?.price_as_of??null,
  breadth:s.market?.breadth??null, spyOk:spy?spy.pass:(s.market?.spy_over_200d??null),
  shapePassed:shape.filter(c=>c.pass).length, shapeTotal:shape.length, rr:finite(rrValue)?rrValue:null, rrOk, veto:vetoed, gateOk,
  ruleOk:rrOk!==false&&vetoed!==true&&shape.every(c=>c.pass), filled:!!t?.outcome.fill_date};
}

export function useSignalRows() {
 const [state,setState]=useState<{loading:boolean;rows:SignalRow[]|null}>({loading:true,rows:null});
 useEffect(()=>{
  const control=new AbortController();let active=true;
  const timeout=setTimeout(()=>control.abort(),15000);
  void (async()=>{
   const [signals,index]=await Promise.all([fetchEvidence('/app/signals.json',validSignals,control.signal),fetchEvidence('/app/tickets/index.json',validIndex,control.signal)]);
   if(!signals){if(active)setState({loading:false,rows:null});return;}
   const ids=new Set((index??[]).map(r=>r.id));
   const tickets=await Promise.all(signals.signals.map(s=>ids.has(s.id)?fetchEvidence(`/app/tickets/${encodeURIComponent(s.id)}.json`,validTicket,control.signal):Promise.resolve(null)));
   clearTimeout(timeout);
   if(active)setState({loading:false,rows:signals.signals.map((s,i)=>toRow(s,tickets[i]&&!tickets[i]!.example?tickets[i]:null))});
  })();
  return()=>{active=false;clearTimeout(timeout);control.abort()};
 },[]);
 return state;
}

// A week's signals are recognised after the first session of the week after next: Friday + 10 days.
export const scanDay = (week:string) => {const d=new Date(week+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+10);return d.toISOString().slice(0,10);};
// The US close (16:00 New York) of a given day, as a UTC timestamp.
export function closeAt(day:string) {
 const noon=new Date(day+'T12:00:00Z');
 const offset=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',timeZoneName:'short'}).formatToParts(noon).find(p=>p.type==='timeZoneName')?.value==='EDT'?4:5;
 return Date.UTC(noon.getUTCFullYear(),noon.getUTCMonth(),noon.getUTCDate(),16+offset);
}
