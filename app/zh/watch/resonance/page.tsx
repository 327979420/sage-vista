"use client";
import {SignalBoard,TrackerShell,useTracker} from "./tracker-ui";
import {useEffect,useState} from "react";

type TestRow={side:"buy"|"sell";factor:string;horizon:number;validation:{samples:number;win_rate:number;trimmed_mean_return:number;median_return:number;mean_adverse:number}};
type Backtest={universe:{eligible:number;events:number};validated_combinations:TestRow[];execution:string;warning:string};

export default function Overview(){
 const data=useTracker();const [study,setStudy]=useState<Backtest|null>(null);
 useEffect(()=>{fetch("/macd-factor-backtest.json").then(x=>x.json()).then(setStudy)},[]);
 return <TrackerShell active="总览" title="MACD 趋势雷达" subtitle="先用MACD和周期建立可复用的看涨／看跌排行榜，再用历史数据验证哪些结构真正有效。">
  {data&&<>
   <section className="rtSummary">
    <article className="rtSummaryPrimary"><small>MACD 看涨候选</small><b>{data.macd_buy_top10.length}</b><p>全部通过固定看涨规则</p></article>
    <article><small>MACD 看跌候选</small><b>{data.macd_sell_top10.length}</b><p>零轴上死叉优先</p></article>
    <article><small>本次扫描</small><b>{data.universe.eligible}</b><p>流动性与历史过滤后</p></article>
    <article><small>看涨榜首</small><b>{data.macd_buy_top10[0]?.symbol??"—"}</b><p>{data.macd_buy_top10[0]?.macd_rank_score??0}规则分 · 可点击核验</p></article>
   </section>
   <section className="rtSystemAudit"><span><small>固定规则</small><b>v{data.ruleset.version}</b></span><span><small>大周期</small><b>完整月线＋完整周线</b></span><span><small>入场时机</small><b>最新完整日线</b></span><span><small>一致性指纹</small><b>{data.consistency_audit.ranking_digest}</b></span><mark>{data.consistency_audit.details_cover_all_published&&!data.consistency_audit.duplicate_symbols?"数据与榜单一致":"审计异常，停止使用"}</mark></section>
   <section className="rtSignals"><div className="rtSectionTitle"><div><p>看涨排行榜</p><h2>当前 MACD 买入结构</h2></div><a href="/zh/watch/resonance/macd">查看看涨 / 看跌完整分榜 →</a></div><p className="rtRankNote">这里只回答MACD结构是否成立，不再使用四层矩阵，也不要求其他指标同时确认。</p><SignalBoard items={data.macd_buy_top10} kind="macd" combined={new Set(data.combined_top10.map(x=>x.symbol))}/></section>
   {study&&<section className="rtSignals"><div className="rtSectionTitle"><div><p>历史事件回测</p><h2>哪些周期组合更有效</h2></div><span>{study.universe.eligible}只历史 · {study.universe.events.toLocaleString()}次信号</span></div><p className="rtRankNote">信号后下一交易日开盘进入。组合先在2024年前发现，再用2025年验证；以下按验证期胜率排序。</p><div className="rtModuleGrid">{study.validated_combinations.slice(0,3).map((x,i)=><article key={`${x.side}-${x.factor}-${x.horizon}`}><small>#{i+1} · {x.side==="buy"?"看涨":"看跌"} · 持有{x.horizon}日</small><h2>{x.factor}</h2><p>验证胜率 {x.validation.win_rate}% · 样本 {x.validation.samples.toLocaleString()}</p><strong>稳健均值 {x.validation.trimmed_mean_return}% · 中位数 {x.validation.median_return}%</strong></article>)}</div><p className="rtRankNote">当前没有看跌组合同时通过“验证期稳健均值为正＋中位数为正”的门槛，因此看跌榜暂时只代表技术转弱观察，不等于做空建议。</p><p className="rtMethod">{study.warning}</p></section>}
   <footer className="rtCompactLinks"><a href="/zh/watch/market">ETF市场环境 →</a><a href="/zh/watch/resonance/requirements">查看MACD规则</a></footer>
  </>}
 </TrackerShell>
}
