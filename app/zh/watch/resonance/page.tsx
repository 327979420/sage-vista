"use client";
import {SignalBoard,TrackerShell,useTracker} from "./tracker-ui";

export default function Overview(){
 const data=useTracker();
 return <TrackerShell active="总览" title="MACD 趋势雷达" subtitle="当前个股排行榜只展示可逐项核验的MACD结构；历史研究与策略表现放在独立页面。">
  {data&&<>
   <section className="rtSummary">
    <article className="rtSummaryPrimary"><small>MACD 看涨候选</small><b>{data.macd_buy_top10.length}</b><p>全部通过固定看涨规则</p></article>
    <article><small>MACD 看跌候选</small><b>{data.macd_sell_top10.length}</b><p>技术转弱观察</p></article>
    <article><small>本次扫描</small><b>{data.universe.eligible}</b><p>流动性与历史过滤后</p></article>
    <article><small>看涨榜首</small><b>{data.macd_buy_top10[0]?.symbol??"—"}</b><p>{data.macd_buy_top10[0]?.macd_rank_score??0}规则分 · 可点击核验</p></article>
   </section>
   <section className="rtSystemAudit"><span><small>固定规则</small><b>v{data.ruleset.version}</b></span><span><small>大周期</small><b>完整月线＋完整周线</b></span><span><small>入场时机</small><b>最新完整日线</b></span><span><small>一致性指纹</small><b>{data.consistency_audit.ranking_digest}</b></span><mark>{data.consistency_audit.details_cover_all_published&&!data.consistency_audit.duplicate_symbols?"数据与榜单一致":"审计异常，停止使用"}</mark></section>
   <section className="rtSignals"><div className="rtSectionTitle"><div><p>当前个股</p><h2>MACD 看涨排行榜</h2></div><a href="/zh/watch/resonance/macd">查看看涨 / 看跌完整分榜 →</a></div><p className="rtRankNote">这里只放当前股票候选，不混入历史策略表现。</p><SignalBoard items={data.macd_buy_top10} kind="macd" combined={new Set()}/></section>
   <footer className="rtCompactLinks"><a href="/zh/watch/resonance/research">查看独立MACD研究与策略表现 →</a><a href="/zh/watch/resonance/requirements">查看MACD规则</a></footer>
  </>}
 </TrackerShell>
}
