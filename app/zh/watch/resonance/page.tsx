"use client";
import {SignalBoard,TrackerShell,useTracker} from "./tracker-ui";

export default function Overview(){
 const data=useTracker();
 return <TrackerShell active="总览" title="今日研究总览" subtitle="先确认最新完整交易日，再看机会、证据和风险。">
  {data&&<>
   <section className="rtTodayBrief">
    <article><small>数据更新到</small><b>{data.as_of}</b><p>最新完整美国交易日</p></article>
    <article><small>今天值得看</small><b>{data.macd_buy_top10[0]?.symbol??"暂无"}</b><p>{data.macd_buy_top10.length?`看涨榜共 ${data.macd_buy_top10.length} 只候选`:"没有有效看涨候选"}</p></article>
    <article><small>为什么值得看</small><b>{data.macd_buy_top10[0]?.chain_reason??"等待新信号"}</b><p>{data.macd_buy_top10[0]?.price_structure.label??"当前无需勉强寻找机会"}</p></article>
    <article className={data.consistency_audit.details_cover_all_published&&!data.consistency_audit.duplicate_symbols?"isHealthy":"isBlocked"}><small>主要风险</small><b>{data.consistency_audit.details_cover_all_published&&!data.consistency_audit.duplicate_symbols?"数据检查通过":"停止使用"}</b><p>{data.consistency_audit.completed_higher_timeframes_only?"周线与月线只用完整周期":"大周期数据异常"}</p></article>
   </section>
   <section className="rtSummary">
    <article className="rtSummaryPrimary"><small>MACD 看涨候选</small><b>{data.macd_buy_top10.length}</b><p>全部通过固定看涨规则</p></article>
    <article><small>MACD 看跌候选</small><b>{data.macd_sell_top10.length}</b><p>技术转弱观察</p></article>
    <article><small>本次扫描</small><b>{data.universe.eligible}</b><p>流动性与历史过滤后</p></article>
    <article><small>看涨榜首</small><b>{data.macd_buy_top10[0]?.symbol??"—"}</b><p>{data.macd_buy_top10[0]?.macd_rank_score??0}规则分 · 可点击核验</p></article>
   </section>
   <details className="rtTechnicalDetails"><summary>查看规则版本与数据审计</summary><div className="rtSystemAudit"><span><small>固定规则</small><b>v{data.ruleset.version}</b></span><span><small>大周期</small><b>完整月线＋完整周线</b></span><span><small>入场时机</small><b>最新完整日线</b></span><span><small>一致性指纹</small><b>{data.consistency_audit.ranking_digest}</b></span><mark>{data.consistency_audit.details_cover_all_published&&!data.consistency_audit.duplicate_symbols?"数据与榜单一致":"审计异常，停止使用"}</mark></div></details>
   <section className="rtSignals"><div className="rtSectionTitle"><div><p>当前个股</p><h2>MACD 看涨排行榜</h2></div><a href="/zh/watch/resonance/macd">查看看涨 / 看跌完整分榜 →</a></div><p className="rtRankNote">这里只放当前股票候选，不混入历史策略表现。</p><SignalBoard items={data.macd_buy_top10} kind="macd" combined={new Set()}/></section>
   <footer className="rtCompactLinks"><a href="/zh/watch/resonance/rare-opportunities">查看多因子雷达 →</a><a href="/zh/watch/resonance/research">查看MACD研究与策略表现</a><a href="/zh/watch/resonance/about">查看功能介绍与使用方法</a></footer>
  </>}
 </TrackerShell>
}
