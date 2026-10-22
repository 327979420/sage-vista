export type TicketIndex = {id:string; symbol:string; signal_week:string; status:string; R:number|null}[];
export type Point = {date:string; price:number};
export type Bar = {date:string; open:number; high:number; low:number; close:number; dif:number; dea:number};
export type Check = {id:string; value:unknown; pass:boolean; derived:boolean};
export type Ticket = {schema_version:1; id:string; symbol:string; signal_week:string; signal_day:string; version:string; example:boolean;
 checks:Check[]; pushes:Point[]; bottoms:Point[]; trend_line:Point[]; weekly:Bar[];
 order:{limit:number;stop:number;target:number;R:number;R_multiple:number;valid_until:string;max_hold_sessions:number;wait_sessions:number;eligible:boolean};
 outcome:{status:string;source:string;source_status?:string;fill_date:string|null;exit_date:string|null;exit:number|null;R:number|null;mark?:number|null;mark_date?:string|null}};
export type Moves = Record<'1w'|'4w'|'13w',{date:string;move_pct:number}|null>;
export type ForwardRow = {id:string;symbol:string;signal_week:string;status:string;moves:Moves;outcome:string|null;R:number|null;exit_date:string|null;
 random:{twins:string;sampled:number;closed:number;median_R:number|null;beat_share:number|null;mean_R:number|null;moves?:Record<'1w'|'4w'|'13w',{median_pct:number;sample:number}|null>;exits?:Record<string,number>|null};
 gross_R:number|null;alert_id:string;lifecycle:{status:string;date:string|null}};
export type Judging = {status:'available'|'missing';completed:number|null;scored:number|null;unscorable:number|null;next_checkpoint:number|null;to_go:number|null;alarm1:boolean|null;verdict:string;alarm2:string;proof:string;
 checkpoints:{k:number;scored:number;unscorable:number;mean_d:number|null;t:number|null;alarm1:boolean;verdict:string}[];
 thresholds:{checkpoints:number[];checkpoint_step:number;alarm1_mean_lt:number;alarm1_t_lte:number;proof_min_trades:number;proof_t_gte:number;satellite_drawdown_gt:number;unscorable_fraction_gt:number}};
export type Forward = {schema_version:1;judging:Judging;as_of:string;outcomes_as_of:string;next_check:string;
 summary:{signals:number;closed:number;average_R:number|null;win_rate:number|null;beat_random_share:number|null;beat_random_signals:number};
 expectation:{average_R:number;win_rate:number;trades:number;label:string;note:string;ledger_heading:string}|null;
 cumulative_R:{date:string;R:number}[];signals:ForwardRow[]};
const obj=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
const optionalNumber=(v:unknown)=>v===null||finite(v);
const date=(v:unknown):v is string=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v);
const optionalDate=(v:unknown)=>v===null||date(v);
export const safeId=(v:unknown):v is string=>typeof v==='string'&&/^[A-Za-z0-9_-]+$/.test(v)&&v!=='index';
export function validIndex(v:unknown):v is TicketIndex {
 return Array.isArray(v)&&v.every(r=>obj(r)&&safeId(r.id)&&typeof r.symbol==='string'&&date(r.signal_week)&&typeof r.status==='string'&&optionalNumber(r.R));
}
export function validTicket(v:unknown):v is Ticket {
 if(!obj(v)||v.schema_version!==1||!safeId(v.id)||typeof v.symbol!=='string'||typeof v.version!=='string'||!date(v.signal_week)||!date(v.signal_day)||typeof v.example!=='boolean')return false;
 if(!Array.isArray(v.checks)||!v.checks.every(c=>obj(c)&&typeof c.id==='string'&&typeof c.pass==='boolean'&&typeof c.derived==='boolean'))return false;
 if(!['pushes','bottoms','trend_line'].every(key=>Array.isArray(v[key])&&(v[key] as unknown[]).every(p=>obj(p)&&date(p.date)&&finite(p.price))))return false;
 if(!Array.isArray(v.weekly)||!v.weekly.length||!v.weekly.every((b,i,a)=>obj(b)&&date(b.date)&&['open','high','low','close','dif','dea'].every(k=>finite(b[k]))&&(i===0||(a[i-1] as Bar).date<b.date)))return false;
 const order=v.order,o=v.outcome;
 return obj(order)&&['limit','stop','target','R','R_multiple','max_hold_sessions','wait_sessions'].every(k=>finite(order[k]))&&date(order.valid_until)&&typeof order.eligible==='boolean'
 &&obj(o)&&typeof o.status==='string'&&typeof o.source==='string'&&optionalDate(o.fill_date)&&optionalDate(o.exit_date)&&optionalNumber(o.exit)&&optionalNumber(o.R);
}
const count=(v:unknown):v is number=>finite(v)&&Number.isInteger(v)&&v>=0;
const publicVerdicts=['继续记录，未证明','失效警报1','暂停判断（对照不足）','需模拟账户，不在公开页'];
function validJudging(v:unknown):v is Judging {
 if(!obj(v)||!['available','missing'].includes(String(v.status))||v.alarm2!=='需模拟账户，不在公开页'||v.proof!=='需模拟账户，不在公开页'||!obj(v.thresholds)||!Array.isArray(v.checkpoints))return false;
 const t=v.thresholds;
 if(JSON.stringify(t.checkpoints)!=='[30,60,100]'||t.checkpoint_step!==100||t.alarm1_mean_lt!==0||t.alarm1_t_lte!==-2||t.proof_min_trades!==100||t.proof_t_gte!==2||t.satellite_drawdown_gt!==.25||t.unscorable_fraction_gt!==.1)return false;
 if(v.status==='missing')return ['completed','scored','unscorable','next_checkpoint','to_go','alarm1'].every(k=>v[k]===null)&&v.checkpoints.length===0&&v.verdict==='本次运行未生成计分';
 if(!['completed','scored','unscorable','next_checkpoint','to_go'].every(k=>count(v[k]))||typeof v.alarm1!=='boolean'||!publicVerdicts.includes(String(v.verdict)))return false;
 const n=v.completed as number, next=n<30?30:n<60?60:n<100?100:(Math.floor(n/100)+1)*100;
 if((v.scored as number)+(v.unscorable as number)!==n||v.next_checkpoint!==next||v.to_go!==next-n)return false;
 const reached=[30,60,...Array.from({length:Math.floor(n/100)},(_,i)=>(i+1)*100)].filter(k=>k<=n);
 return v.checkpoints.length===reached.length&&v.checkpoints.every((c,i)=>obj(c)&&c.k===reached[i]&&count(c.scored)&&count(c.unscorable)&&c.scored+c.unscorable===c.k&&optionalNumber(c.mean_d)&&optionalNumber(c.t)&&typeof c.alarm1==='boolean'&&publicVerdicts.includes(String(c.verdict)));
}
export function validForward(v:unknown):v is Forward {
 if(!obj(v)||!validJudging(v.judging)||v.schema_version!==1||!date(v.as_of)||typeof v.outcomes_as_of!=='string'||typeof v.next_check!=='string'||!obj(v.summary))return false;
 const s=v.summary;
 if(!['signals','closed','beat_random_signals'].every(k=>finite(s[k]))||!['average_R','win_rate','beat_random_share'].every(k=>optionalNumber(s[k])))return false;
 if(v.expectation!==null&&(!obj(v.expectation)||!['average_R','win_rate','trades'].every(k=>finite((v.expectation as Record<string,unknown>)[k]))||!['label','note','ledger_heading'].every(k=>typeof (v.expectation as Record<string,unknown>)[k]==='string')))return false;
 if(!Array.isArray(v.cumulative_R)||!v.cumulative_R.every(p=>obj(p)&&date(p.date)&&finite(p.R)))return false;
 return Array.isArray(v.signals)&&v.signals.every(r=>obj(r)&&safeId(r.id)&&typeof r.symbol==='string'&&date(r.signal_week)&&typeof r.status==='string'&&optionalNumber(r.R)&&optionalDate(r.exit_date)&&obj(r.moves)
 &&['1w','4w','13w'].every(k=>{const m=(r.moves as Record<string,unknown>)[k];return m===null||(obj(m)&&date(m.date)&&finite(m.move_pct))})
 &&obj(r.random)&&typeof r.random.twins==='string'&&finite(r.random.closed)&&finite(r.random.sampled)&&['median_R','mean_R','beat_share'].every(k=>optionalNumber((r.random as Record<string,unknown>)[k]))
 &&!('blind' in r)&&optionalNumber(r.gross_R)&&typeof r.alert_id==='string'&&/^A-[A-Za-z0-9_-]{6,8}$/.test(r.alert_id)
 &&obj(r.lifecycle)&&['waiting','filled','target','stopped','time','cancelled','expired','skipped','unverified'].includes(String(r.lifecycle.status))&&optionalDate(r.lifecycle.date));
}
export async function fetchEvidence<T>(url:string, valid:(v:unknown)=>v is T, signal:AbortSignal,fetcher:typeof fetch=fetch):Promise<T|null> {
 try {const r=await fetcher(url,{cache:'no-store',signal});if(!r.ok)return null;const value:unknown=await r.json();return valid(value)?value:null}catch{return null}
}
export const orderedTickets=(rows:TicketIndex)=>[...rows].sort((a,b)=>b.signal_week.localeCompare(a.signal_week)||a.id.localeCompare(b.id));
