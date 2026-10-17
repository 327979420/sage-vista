'use client';
import type {Today} from './data';
import {Header,Missing,Source,DataDate,percent,useReport} from './shared';
import {strings as s} from './strings';
export function TodayView({data}:{data:Today}) {
  const m=data.market;
  return <><DataDate date={data.as_of}/>{Object.keys(data.stale).length>0&&<aside className="svAppWarning"><strong>{s.stale}</strong><p>{s.staleDetail}</p><details><summary>{Object.keys(data.stale).length} · {s.stale}</summary><ul>{Object.entries(data.stale).map(([key,date])=><li key={key}>{s.inputName(key)}：{date??s.unknownDate}</li>)}</ul></details></aside>}
    <div className="svAppGrid">
      <section className="svAppCard"><h2>{s.market}</h2><div className="svAppLight" data-light={m.light??'unknown'}>{m.light?s.lights[m.light]:s.unavailable}</div>{m.light&&<p>{s.verdict[m.light]}</p>}<p>{m.spy_over_200d===null?s.spyMissing:m.spy_over_200d?s.spyAbove:s.spyBelow}</p><p>{m.breadth===null?s.breadthMissing:s.breadth(percent(m.breadth*100,0))}</p><Source rule={`${s.marketRule} · ${data.breadth_source} · ${s.breadthSample}：${m.breadth_sample??s.unavailable}`}/></section>
      <section className="svAppCard"><h2>{s.newSignals}</h2><div className="svAppMetrics"><div><span>{s.signalCount}</span><strong>{data.new_signals_this_week}</strong></div><div><span>{s.orders}</span><strong>{data.orders_to_place}</strong></div></div><p className="svAppMeta">{s.signalWeek}：{data.signal_week}</p><p>{s.signalExplanation}</p><Source rule={s.signalRule}/></section>
      <section className="svAppCard"><h2>{s.monthEnd}</h2><strong>{data.month_end.rebalance_due?s.due:s.notDue}</strong><p>{s.switches}：{data.month_end.would_switch.length?data.month_end.would_switch.join('、'):s.noSwitch}</p><p>{s.nextSession}：{data.month_end.next_session}</p><p className="svAppMeta">{s.switchNote}</p><Source rule={s.sectorRule}/></section>
      <section className="svAppCard"><h2>{s.tasks}</h2>{data.this_week.length?<ul>{data.this_week.map((a,i)=><li key={a.signal_id??i}>{a.kind==='new_order'?`${a.symbol} · ${s.newOrder}`:s.rebalance}</li>)}</ul>:<p>{s.noTasks}</p>}<Source rule={`${s.signalRule} · ${s.sectorRule}`}/></section>
    </div></>;
}
export default function TodayPage() {const state=useReport('today');return <><Header current="today"/><main><h1>{s.today}</h1>{state.data?<TodayView data={state.data}/>:<Missing loading={state.loading}/>}</main></>}
