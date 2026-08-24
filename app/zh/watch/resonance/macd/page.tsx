"use client";
import {SignalBoard,TrackerShell,useTracker} from "../tracker-ui";
export default function Macd(){const data=useTracker();return <TrackerShell active="MACD" title="MACD 多周期观察" subtitle="零轴下优先，观察日线向周线、月线传导。">{data&&<section className="rtSignals"><div className="rtSectionTitle"><div><p>MACD TOP 10</p><h2>只展示MACD证据</h2></div><span>旧金叉与死叉分开处理</span></div><SignalBoard items={data.macd_top10} kind="macd" combined={new Set(data.combined_top10.map(x=>x.symbol))}/></section>}</TrackerShell>}

