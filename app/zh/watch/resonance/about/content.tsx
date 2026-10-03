"use client";
import {Fragment, type ReactNode} from "react";
import {useLocale} from "../../../../i18n/locale";

// About SV, written in both languages side by side (long formatted copy reads
// better than catalog fragments). Every factual claim mirrors the production
// rules in docs/rules/04_SCORING.md and 07_RANKING_AND_TRACKING.md.
type Step={icon:string;title:string;body:string};
type Copy={
 lead:string[];pillarsIntro:string;pillars:Step[];pillarsOutro:string;
 howTitle:string;how:Step[];tip:string;
 defineTitle:string;define:string;checklistIntro:string;checklist:string[];checklistOutro:string;stages:Step[];
 checkTitle:string;checks:Step[];disclaimer:string;
};

const en:Copy={
 lead:["**Sage Vista (SV) is the trading system I built and use for my own trading.** Its job is to remind you what opportunities the market is offering, and those opportunities are defined by well-documented methods, not gut feel: Alexander Elder's **Triple Screen trading system**, described in his book Trading for a Living, and the classic **trend-pullback** approach. In plain terms, SV looks for strong stocks pulling back inside a long-term uptrend, with a clear setup to act on. Each US trading day it reviews about 1,500 stocks and keeps a short, ranked list of the ones that fit, with the exact evidence behind every score."],
 pillarsIntro:"Around that list, SV gives you the rest of the picture in one place:",
 pillars:[
  {icon:"🌐",title:"Market",body:"How broad the market really is, and whether money and positioning support the move."},
  {icon:"🧩",title:"Sectors",body:"Which of 26 themes are leading."},
  {icon:"📈",title:"Technicals",body:"Every stock's monthly, weekly and daily setup."},
 ],
 pillarsOutro:"The goal is a full view of the market that's quick and easy to read. SV doesn't place trades for you: it shows you where to look and why, and the decision stays yours.",
 howTitle:"🗺️ How to use SV: top down, in about ten minutes",
 how:[
  {icon:"📊",title:"Market: is it a good day to look for longs?",body:"Open **Market** and read the **Market Read** line at the top. Then check **Market Participation** (how many of 1,172 stocks are above their 20/50/200-day averages), **Market Breakouts** (new highs vs. new lows) and **Market Leadership** (whether equal-weight and small caps keep up with the S&P 500). Broad, rising participation means pullbacks are more likely to be bought; narrow leadership means be pickier. The weekly and monthly sections (futures positioning, margin debt) show whether the bigger crowd is stretched."},
  {icon:"🧭",title:"Sectors: where is the strength?",body:"Open **Sectors** to see which of the 26 themes are moving, from semiconductors and AI infrastructure to uranium and grid power. Each theme is tied to a reference ETF and its holdings, and lists the SV candidates that belong to it. A setup inside a leading theme deserves more attention than the same setup in a lagging one."},
  {icon:"🎯",title:"Stocks: which names, and why?",body:"Open **Multi-Factor Opportunities**. **New nominations** are today's fresh setups; the **Watchlist** holds names whose setups are still intact. Use **Review first** for the top-ranked names or **Strong monthly** for the strongest long-term trends, and click any column header to sort. Click a stock to expand its verdict and setup tags; **Full summary** shows its monthly, weekly and daily scores, every check it passed, the factors that fired, and the level where the setup breaks."},
 ],
 tip:"⚡ For faster, short-term ideas, **Daily Setups** scans the day's 100 most-traded stocks for clean pullback shapes.",
 defineTitle:"🧠 How SV defines an opportunity",
 define:"SV follows one of the oldest ideas in technical trading, **buying pullbacks in an uptrend**, and makes every step explicit. It is modelled on Elder's **Triple Screen**: the long-term trend sets the direction, a pullback creates the opportunity, and a short-term signal times the entry. SV runs these three screens on monthly, weekly and daily charts.",
 checklistIntro:"A stock passes the first screen, a **regime filter**, only when:",
 checklist:["its monthly trend allows it and its weekly trend agrees","it isn't stretched near a monthly high","it has pulled back from its 60-day high","it trades enough volume to be practical"],
 checklistOutro:"About two-thirds of stocks stop here.",
 stages:[
  {icon:"🪝",title:"1. The pullback setup: where the reaction should end",body:"A new nomination needs one of three entry setups (a **double-bottom MACD cross**, a **three-push breakout** or a **support reversal**) plus a fresh MACD cross on the daily chart. Support tests are read with care: a dip below support that is quickly reclaimed (a **spring**, or **liquidity sweep**) still counts; a close that stays below it does not. A listed stock stays on the watchlist until a close breaks below the structure that put it there."},
  {icon:"🧮",title:"2. Multi-timeframe confluence score",body:"Each stock is checked against the same 26 factors on its monthly, weekly and daily charts: **support** (20/50/100/200-day moving averages, Fibonacci 0.5/0.618 and the Golden Pocket, volume-profile peaks, repeated bottoms), **reversal candles** (engulfing, hammer, doji), **momentum** (Gerald Appel's MACD and J. Welles Wilder's RSI divergence) and **volume** (spikes, and volume at support). Similar signals are capped so one idea can't be counted twice, and the three timeframes are weighted **3:2:1**, so agreement on the bigger charts counts most."},
  {icon:"🔄",title:"3. Context, then daily re-scoring",body:"Each candidate links to its **sector-rotation** context: which of SV's 26 themes it belongs to, and how that theme's ETF is moving in **relative strength**. After every US close the list is re-scored. Nominations are never rewritten, so “since listing” always starts from the day SV actually flagged the stock."},
 ],
 checkTitle:"🔬 Built to be checked",
 checks:[
  {icon:"🕒",title:"Point-in-time data",body:"Only completed bars are used. No look-ahead."},
  {icon:"🧪",title:"Out-of-sample",body:"Built on 2000–2024, validated on 2025, tracked live in 2026."},
  {icon:"⚖️",title:"A score is a priority, not a probability",body:"It ranks what to review first. It isn't a win rate."},
 ],
 disclaimer:"⚠️ A research tool, not investment advice. Stocks come from SV's own pool of about 1,500 US stocks, not the whole market; every trading decision is yours.",
};

const zh:Copy={
 lead:["**Sage Vista（SV）是我自己搭建、并在实际交易中使用的交易系统。** 它的作用是提醒你市场上正在出现哪些机会；这些机会不是凭感觉定义的，而是依据有公开文献、经过长期检验的方法：亚历山大·埃尔德（Alexander Elder）在《以交易为生》中提出的**三重滤网交易系统**，以及经典的**顺势回调**思路。简单说，SV 寻找的是长期上升趋势中正在回调、并出现清晰入场形态的强势股。每个美股交易日，它复评约 1,500 只股票，只保留符合条件的少数股票并排序，每个分数背后的证据都清楚可查。"],
 pillarsIntro:"除了这份榜单，SV 还把其他信息放在同一个地方：",
 pillars:[
  {icon:"🌐",title:"大盘",body:"市场参与到底有多广，资金与仓位是否支持当前走势。"},
  {icon:"🧩",title:"行业",body:"26 个主题中哪些正在领涨。"},
  {icon:"📈",title:"技术面",body:"每只股票在月线、周线、日线上的形态。"},
 ],
 pillarsOutro:"目标是让你快速、轻松地看清整个市场。SV 不会替你下单：它告诉你该看哪里、为什么看，决定始终由你来做。",
 howTitle:"🗺️ 如何使用 SV：自上而下，大约十分钟",
 how:[
  {icon:"📊",title:"大盘：今天适合找做多机会吗？",body:"打开**大盘**，先读顶部的**市场概况**。再看**市场参与**（1,172 只股票中有多少站上 20／50／200 日均线）、**市场突破**（新高与新低）和**市场领导力**（等权与小盘股是否跟上标普 500）。参与面广且在扩大，回调更容易被买入；领涨面窄，就要更挑剔。每周与每月部分（期货仓位、融资余额）可以看出大资金是否已经过度拥挤。"},
  {icon:"🧭",title:"行业：强势在哪里？",body:"打开**行业**，看 26 个主题中哪些在动，从半导体、AI 基础设施到铀矿和电网。每个主题都对应一只参考 ETF 及其持仓，并列出属于该主题的 SV 候选股。同样的形态，出现在领涨主题里，比出现在落后主题里更值得关注。"},
  {icon:"🎯",title:"个股：看哪些、为什么？",body:"打开**多因子机会**。**新提名**是当天新出现的形态；**持续观察**是形态仍然有效的股票。用**优先复核**看排名最高的股票，用**月线强势**看长期趋势最强的股票，点击表头可以排序。点击股票即可展开结论与门票标签；**查看完整摘要**会显示月、周、日分数、通过的每项检查、命中的因子，以及形态失效的价位。"},
 ],
 tip:"⚡ 想找更快的短线机会，**我最喜欢形态**会在当天成交额最大的 100 只股票里寻找清晰的回调形态。",
 defineTitle:"🧠 SV 如何定义机会",
 define:"SV 采用技术交易中最经典的思路之一——**在上升趋势中买回调**，并把每一步都写清楚。它以埃尔德的**三重滤网**为原型：长期趋势决定方向，回调创造机会，短期信号把握入场时机。SV 在月线、周线、日线上依次执行这三层滤网。",
 checklistIntro:"只有同时满足以下条件，股票才能通过第一层滤网（**方向过滤**）：",
 checklist:["月线方向获得许可，且周线确认","没有处于月线高位区","相对前 60 日高点已有回调","成交额足够，具备可交易性"],
 checklistOutro:"通常约三分之二的股票在这一步被排除。",
 stages:[
  {icon:"🪝",title:"1. 回调形态：回调应在哪里结束",body:"新提名需要三类门票之一——**两底金叉**、**三推突破**或**支撑反转**——并且日线出现新的 MACD 金叉。支撑测试会被谨慎解读：短暂跌破支撑后迅速收回（**弹簧形态**，或称**流动性扫荡**）仍然有效；收盘持续停留在支撑下方则不算。已入选的股票会一直留在持续观察，直到收盘跌破让它入选的结构。"},
  {icon:"🧮",title:"2. 多周期共振评分",body:"每只股票在月线、周线、日线上都用同一套 26 个因子检查：**支撑**（20／50／100／200 日均线、斐波那契 0.5／0.618 与黄金口袋、成交量分布峰、多次探底）、**反转 K 线**（吞没、锤头、十字星）、**动能**（杰拉德·阿佩尔的 MACD 与 J. 韦尔斯·怀尔德的 RSI 背离）以及**成交量**（突然放量、支撑位放量）。同类信号设有上限，避免同一个想法被重复计分；三个周期再按 **3∶2∶1** 加权，大周期的共振权重最高。"},
  {icon:"🔄",title:"3. 结合背景，每日复评",body:"每只候选股都会关联它的**板块轮动**背景：属于 SV 26 个主题中的哪一个，以及该主题 ETF 的**相对强弱**走势。每个美股交易日收盘后，整份榜单都会重新评分。原提名永远不会改写，所以“上榜后涨跌”始终从 SV 实际提名当天开始计算。"},
 ],
 checkTitle:"🔬 可以被检验",
 checks:[
  {icon:"🕒",title:"时点数据",body:"只使用已经完整收盘的 K 线，没有未来函数。"},
  {icon:"🧪",title:"样本外验证",body:"2000—2024 年开发，2025 年验证，2026 年实盘跟踪。"},
  {icon:"⚖️",title:"分数是优先级，不是概率",body:"它决定先复核什么，不是胜率。"},
 ],
 disclaimer:"⚠️ 研究工具，不构成投资建议。股票来自 SV 自己约 1,500 只美股的观察池，不代表整个市场；每一个交易决定都由你来做。",
};

export const aboutCopy={en,zh};

// **bold** is the only markup in the copy.
function rich(text:string):ReactNode{
 return text.split("**").map((part,i)=>i%2?<b key={i}>{part}</b>:<Fragment key={i}>{part}</Fragment>);
}

export default function AboutContent(){
 const {locale}=useLocale();
 const c=locale==="en"?en:zh;
 return <article className="svAbout">
  <section className="svAboutLead">{c.lead.map((p,i)=><p key={i}>{rich(p)}</p>)}
   <p>{c.pillarsIntro}</p>
   <ul className="svAboutPillars">{c.pillars.map(p=><li key={p.title}><span aria-hidden="true">{p.icon}</span><b>{p.title}</b><p>{p.body}</p></li>)}</ul>
   <p>{c.pillarsOutro}</p>
  </section>
  <section className="svAboutSection" id="how-to-use"><h2>{c.howTitle}</h2>
   <ol className="svAboutSteps">{c.how.map((s,i)=><li key={s.title}><span className="svAboutStepNo">{i+1}</span><h3><span aria-hidden="true">{s.icon}</span> {s.title}</h3><p>{rich(s.body)}</p></li>)}</ol>
   <p className="svAboutTip">{rich(c.tip)}</p>
  </section>
  <section className="svAboutSection"><h2>{c.defineTitle}</h2><p>{rich(c.define)}</p>
   <div className="svAboutChecklist"><p>{rich(c.checklistIntro)}</p><ul>{c.checklist.map(x=><li key={x}><span aria-hidden="true">✅</span> {x}</li>)}</ul><p>{c.checklistOutro}</p></div>
   <div className="svAboutStages">{c.stages.map(s=><div key={s.title}><h3><span aria-hidden="true">{s.icon}</span> {s.title}</h3><p>{rich(s.body)}</p></div>)}</div>
  </section>
  <section className="svAboutSection"><h2>{c.checkTitle}</h2>
   <ul className="svAboutChecks">{c.checks.map(s=><li key={s.title}><span aria-hidden="true">{s.icon}</span><b>{s.title}</b><p>{s.body}</p></li>)}</ul>
  </section>
  <p className="svAboutNote">{c.disclaimer}</p>
 </article>;
}
