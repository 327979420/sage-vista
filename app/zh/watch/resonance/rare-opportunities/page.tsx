"use client";
import {useEffect,useState} from "react";
import {TrackerShell} from "../tracker-ui";

type Signal={symbol:string;date:string;price:number;score:number;official_score?:number;observational_score?:number;risk_deduction?:number;total_score?:number;level:string;components:string[];important_misses?:string[];category_scores?:Record<string,number>;risks?:string[]};
type Example={symbol:string;date:string;entry_date:string;signal_close:number;entry_open:number;score:number;components:string[];return_20d:number|null;return_100d:number|null;listing_status:string};
type Radar={generated_at:string;as_of:string;registry_version?:string;policy:string;score_policy?:Record<string,string>;scan:{frequency:string;universe_scanned:number;future_data_used:boolean};signals:Signal[];historical_examples:Example[]};
type Registry={registry_version:string;factor_count:number};

export default function RareOpportunities(){
 const [data,setData]=useState<Radar|null>(null),[registry,setRegistry]=useState<Registry|null>(null);
 useEffect(()=>{fetch("/rare-opportunity-radar.json").then(x=>x.json()).then(setData);fetch("/factor-registry.json").then(x=>x.json()).then(setRegistry)},[]);
 return <TrackerShell active="多因子雷达" title="多因子雷达" subtitle="基础资格＋正式分＋观察分－风险扣分；当前六因子仍只计观察分。">
  <div className="rareRadar">{data&&<>
   <section className="rareFirstView">
    <article><small>数据更新到</small><b>{data.as_of}</b><p>{data.scan.future_data_used?"数据异常，停止使用":"完整收盘数据 · 未使用未来数据"}</p></article>
    <article><small>今天值得看</small><b>{data.signals.length} 只</b><p>{data.signals.length?"达到当前稀有观察门槛":"没有达到门槛，保持安静"}</p></article>
    <article><small>为什么值得看</small><b>{data.signals[0]?.components.slice(0,2).join("＋")??"暂无稀有组合"}</b><p>{data.signals[0]?`观察分 ${data.signals[0].observational_score??data.signals[0].score}`:"不为每天有内容而降低门槛"}</p></article>
    <article><small>主要风险</small><b>正式分 0</b><p>固定六因子尚未跨时期验证，不代表胜率</p></article>
   </section>
   <div className="rareRegistryLine"><span>因子注册表 v{data.registry_version??registry?.registry_version??"0.1.0"}</span><span>{registry?.factor_count??25} 个已定义因子</span><span>当前：观察模式</span></div>
   <section className="rareCurrent"><header><div><small>最新观察</small><h2>今天有没有稀有机会？</h2></div><mark>研究提醒，不是自动买入</mark></header>{data.signals.length?<div>{data.signals.map(x=><article key={x.symbol} className="rareSignal"><header><b>{x.symbol}</b><strong>{x.total_score??x.score}分 · {x.level}</strong></header><p>${x.price} · {x.date}</p><div className="rareScoreSplit"><span><small>正式分</small><b>{x.official_score??0}</b></span><span><small>观察分</small><b>{x.observational_score??x.score}</b></span><span><small>风险扣分</small><b>−{x.risk_deduction??0}</b></span></div>{x.category_scores&&<div className="rareCategories">{Object.entries(x.category_scores).map(([k,v])=><span key={k}>{k}<b>{v}</b></span>)}</div>}<ul>{x.components.map(c=><li key={c}>✓ {c}</li>)}</ul>{x.important_misses?.length?<p className="rareMisses"><b>重要未命中：</b>{x.important_misses.join("、")}</p>:null}{x.risks?.length?<p className="rareRisks"><b>风险：</b>{x.risks.join("；")}</p>:null}</article>)}</div>:<div className="rareEmpty"><b>今天没有达到门槛的信号</b><p>这是正常结果。系统不会为了每天有内容而降低门槛。</p></div>}</section>
   <details className="rareLegacy"><summary>查看当前过渡评分规则</summary><div><p>基础资格：长期趋势未破坏、从60日高点明显回调、日线MACD完整收盘金叉。</p><p>观察分：Fibonacci、EMA、完整周线MACD改善、三推趋势线、上方未补缺口、Bullish FVG，共六项。</p><p>正式分：当前为0。只有完成开发期、2025验证期和2026前向观察并处理重复关系后，因子才可能晋级。</p></div></details>
   <section className="rareExamples"><header><div><small>历史复查</small><h2>成功和失败案例都保留</h2></div><span>下一日开盘进入，仅用于核验</span></header>{data.historical_examples.length?<div>{data.historical_examples.map(x=><article key={`${x.symbol}-${x.date}`}><header><div><b>{x.symbol}</b><small>{x.date} 触发 · {x.entry_date} 开盘观察</small></div><mark>{x.score}分</mark></header><p>信号价 ${x.signal_close} · 次日开盘 ${x.entry_open}</p><div>{x.components.map(c=><span key={c}>{c}</span>)}</div><footer><b>20日：{x.return_20d===null?"尚未走完":`${x.return_20d>0?"+":""}${x.return_20d}%`}</b><b>100日：{x.return_100d===null?"尚未走完":`${x.return_100d>0?"+":""}${x.return_100d}%`}</b></footer></article>)}</div>:<div className="rareEmpty"><b>历史案例正在生成</b></div>}</section>
  </>}</div>
 </TrackerShell>
}
