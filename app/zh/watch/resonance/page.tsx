"use client";
import {ConfluenceMatrix,SignalBoard,TrackerShell,useTracker} from "./tracker-ui";
import {useState} from "react";

export default function Overview(){
 const data=useTracker();
 const [direction,setDirection]=useState<"buy"|"sell">("buy");
 return <TrackerShell active="总览" title="指标共振" subtitle="MACD、RSI、EMA与价格突破分别验证；点击任何标的可查看完整证据。">
  {data&&<>
   <section className="rtSummary">
    <article className="rtSummaryPrimary"><small>四重看涨共振</small><b>{data.four_layer_bullish.length}</b><p>四层全部发出看涨信息</p></article>
    <article><small>四重看跌共振</small><b>{data.four_layer_bearish.length}</b><p>四层全部发出看跌信息</p></article>
    <article><small>本次扫描</small><b>{data.universe.eligible}</b><p>严格流动性与历史过滤</p></article>
    <article><small>MACD 看涨榜首</small><b>{data.macd_buy_top10[0]?.symbol??"—"}</b><p>{data.macd_buy_top10[0]?.macd_rank_score??0}规则分 · 可点击核验</p></article>
   </section>
   <section className="rtSystemAudit"><span><small>固定规则</small><b>v{data.ruleset.version}</b></span><span><small>方向确认</small><b>完整月线＋完整周线</b></span><span><small>时机确认</small><b>最新完整日线</b></span><span><small>一致性指纹</small><b>{data.consistency_audit.ranking_digest}</b></span><mark>{data.consistency_audit.details_cover_all_published&&!data.consistency_audit.duplicate_symbols?"数据与榜单一致":"审计异常，停止使用"}</mark></section>
   <section className="rtSignals"><div className="rtSectionTitle"><div><p>第一优先级</p><h2>MACD 看涨候选</h2></div><a href="/zh/watch/resonance/macd">查看完整买入 / 卖出分榜 →</a></div><p className="rtRankNote">这里不要求 RSI、EMA 或突破同时确认；它回答的唯一问题是：哪些股票当前的 MACD 看涨结构最清楚。</p><SignalBoard items={data.macd_buy_top10.slice(0,5)} kind="macd" combined={new Set(data.combined_top10.map(x=>x.symbol))}/></section>
   <section className="rtSignals">
    <div className="rtSectionTitle"><div><p>四层一致性矩阵</p><h2>看涨与看跌分开排名</h2></div><div className="rtDirectionTabs"><button className={direction==="buy"?"active":""} onClick={()=>setDirection("buy")}>看涨观察</button><button className={direction==="sell"?"active":""} onClick={()=>setDirection("sell")}>看跌观察</button></div></div>
    <p className="rtRankNote">看涨默认展示；看跌必须使用镜像逻辑。零轴下死叉不作强看跌，超卖或底背离会触发反弹风险。</p>
    <ConfluenceMatrix items={direction==="buy"?data.bullish_watch_top10:data.bearish_watch_top10} details={data.details} method={data.ranking_method}/>
   </section>
   <section className="rtModuleGrid">
    <a href="/zh/watch/resonance/confluence"><small>严格复核</small><h2>MACD＋RSI</h2><p>核对新鲜金叉、能量变化与新鲜RSI背离。</p><strong>{data.combined_top10.length}只 →</strong></a>
    <a href="/zh/watch/resonance/macd"><small>金叉位置＋能量</small><h2>MACD</h2><p>零轴下金叉优先，并展示能量柱增强或衰减。</p><strong>查看TOP 10 →</strong></a>
    <a href="/zh/watch/resonance/rsi"><small>超卖与背离</small><h2>RSI</h2><p>查看底背离、顶背离与修复状态。</p><strong>查看TOP 10 →</strong></a>
    <a href="/zh/watch/resonance/volume"><small>独立增强证据</small><h2>成交量</h2><p>放量只作确认，不单独称为买点。</p><strong>{data.volume_top10.length}个提醒 →</strong></a>
   </section>
   <footer className="rtCompactLinks"><a href="/zh/watch/market">ETF市场环境 →</a><a href="/zh/watch/resonance/requirements">查看规则</a></footer>
  </>}
 </TrackerShell>
}
