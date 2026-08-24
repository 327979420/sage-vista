"use client";
import {ConfluenceMatrix,TrackerShell,useTracker} from "./tracker-ui";
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
    <article><small>看涨观察榜首</small><b>{data.bullish_watch_top10[0]?.symbol??"—"}</b><p>{data.bullish_watch_top10[0]?.ranking_score??0}分 · 可点击核验</p></article>
   </section>
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
