export type Quote = {price_as_of: string|null; close: number|null; sma200: number|null; distance_pct: number|null; stale: boolean};
export type Today = {schema_version: number; as_of: string; breadth_source: string; market: Quote & {light:'green'|'amber'|'red'|null; spy_over_200d:boolean|null; breadth:number|null; breadth_sample:number|null}; signal_week:string; new_signals_this_week:number; orders_to_place:number; month_end:{rebalance_due:boolean; next_session:string; would_switch:string[]}; stale:Record<string,string|null>; this_week:{kind:'new_order'|'month_end_rebalance'; symbol?:string; signal_id?:string}[]};
export type Portfolio = {schema_version:number; as_of:string; status:string; month_end_signal_as_of:string; sleeves:{symbol:string; today:Quote & {hold:string|null}; month_end:Quote & {hold:string|null}; would_switch:boolean|null; stale:boolean}[]};
export type Signals = {schema_version:number; as_of:string; signals:{id:string; symbol:string; status:string; quote:Quote; distances:{to_stop_pct:number|null; to_target_pct:number|null; to_stop_R:number|null; to_target_R:number|null}|null}[]};
export type Reports = {today:Today; portfolio:Portfolio; signals:Signals};
const object = (v:unknown):v is Record<string,unknown> => v !== null && typeof v === 'object' && !Array.isArray(v);
const number = (v:unknown) => typeof v === 'number' && Number.isFinite(v);
const nullableNumber = (v:unknown) => v === null || number(v);
const nullableString = (v:unknown) => v === null || typeof v === 'string';
const nullableBool = (v:unknown) => v === null || typeof v === 'boolean';
const quote = (v:unknown):boolean => object(v) && nullableString(v.price_as_of) && ['close','sma200','distance_pct'].every(k=>nullableNumber(v[k])) && typeof v.stale === 'boolean';
export function validReport<K extends keyof Reports>(kind:K, v:unknown):v is Reports[K] {
  if (!object(v) || v.schema_version !== 1 || typeof v.as_of !== 'string') return false;
  if (kind === 'today') {
    const m=v.market, end=v.month_end;
    return object(m) && quote(m) && [null,'green','amber','red'].includes(m.light as string|null) && nullableBool(m.spy_over_200d) && nullableNumber(m.breadth) && (m.breadth_sample === null || (Number.isInteger(m.breadth_sample) && (m.breadth_sample as number)>=0))
      && typeof v.breadth_source === 'string' && typeof v.signal_week === 'string'
      && [v.new_signals_this_week,v.orders_to_place].every(n=>number(n) && Number.isInteger(n) && (n as number)>=0)
      && object(end) && typeof end.rebalance_due === 'boolean' && typeof end.next_session === 'string'
      && Array.isArray(end.would_switch) && end.would_switch.every(s=>typeof s === 'string')
      && object(v.stale) && Object.values(v.stale).every(nullableString)
      && Array.isArray(v.this_week) && v.this_week.every(a=>object(a) && (a.kind === 'month_end_rebalance' || (a.kind === 'new_order' && typeof a.symbol === 'string')));
  }
  if (kind === 'portfolio') return typeof v.status === 'string' && typeof v.month_end_signal_as_of === 'string'
    && Array.isArray(v.sleeves) && v.sleeves.length === 10 && v.sleeves.every(s=>object(s) && typeof s.symbol === 'string' && quote(s.today) && quote(s.month_end) && object(s.today) && object(s.month_end) && nullableString(s.today.hold) && nullableString(s.month_end.hold) && nullableBool(s.would_switch) && typeof s.stale === 'boolean');
  return Array.isArray(v.signals) && v.signals.every(s=>object(s) && typeof s.id === 'string' && typeof s.symbol === 'string' && typeof s.status === 'string' && quote(s.quote) && (s.distances === null || (object(s.distances) && ['to_stop_pct','to_target_pct','to_stop_R','to_target_R'].every(k=>nullableNumber((s.distances as Record<string,unknown>)[k])))));
}
export async function fetchReport<K extends keyof Reports>(kind:K, signal:AbortSignal, fetcher:typeof fetch = fetch):Promise<Reports[K]|null> {
  try {
    const response = await fetcher(`/app/${kind}.json`, {cache:'no-store',signal});
    if (!response.ok) return null;
    const value:unknown = await response.json();
    return validReport(kind,value) ? value : null;
  } catch { return null; }
}
export const trend = (q:Quote) => q.close === null || q.sma200 === null ? null : q.close > q.sma200;
export const openPositions = (data:Signals) => data.signals.filter(s=>s.status === 'open');
export const emptySlots = (data:Signals) => Math.max(0,10-openPositions(data).length);
