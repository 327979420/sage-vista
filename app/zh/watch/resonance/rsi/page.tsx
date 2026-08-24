"use client";
import {SignalBoard,TrackerShell,useTracker} from "../tracker-ui";
export default function Rsi(){const data=useTracker();return <TrackerShell active="RSI" title="RSI 超卖与底背离" subtitle="价格创新低而RSI低点抬高，且结构必须保持新鲜。">{data&&<section className="rtSignals"><div className="rtSectionTitle"><div><p>RSI TOP 10</p><h2>只展示RSI证据</h2></div><span>第二低点需在最近8根K线内</span></div><SignalBoard items={data.rsi_top10} kind="rsi" combined={new Set(data.combined_top10.map(x=>x.symbol))}/></section>}</TrackerShell>}

