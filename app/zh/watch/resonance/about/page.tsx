import {TrackerShell} from "../tracker-ui";

const sections=[
 {number:"01",title:"先看总览",body:"先确认数据日期和系统状态，再看今天是否出现值得复核的 MACD 或多因子候选。没有信号是正常结果。"},
 {number:"02",title:"再核验证据",body:"打开候选，逐项检查周期、价格结构、RSI、量能与风险。分数用于整理证据，不代表收益概率。"},
 {number:"03",title:"最后看研究",body:"进入 MACD 研究查看规则、样本、20/100 日结果、失败原因和跨时期稳定性，再决定是否继续观察。"},
];

export default function About(){
 return <TrackerShell active="功能介绍" title="如何使用 Sage Vista" subtitle="一个可解释、可人工复核的美股 MACD 日终研究工具。">
  <section className="rtAboutLead">
   <div><small>使用原则</small><h2>先确认数据，再看机会；先核验证据，再谈结论。</h2></div>
   <p>Sage Vista 不自动下单，也不把规则匹配分数包装成胜率。所有信号只使用当时已经完整收盘的数据；历史回测按下一交易日复权开盘价进入。</p>
  </section>
  <section className="rtAboutSteps">{sections.map(x=><article key={x.number}><small>{x.number}</small><h2>{x.title}</h2><p>{x.body}</p></article>)}</section>
  <section className="rtAboutGrid">
   <article><small>总览</small><h2>今天有什么值得看</h2><p>汇总最新交易日、候选数量、系统健康和最值得优先复核的对象。</p></article>
   <article><small>MACD</small><h2>方向与时机</h2><p>查看完整日线、周线和月线状态，以及金叉或死叉是否仍然新鲜有效。</p></article>
   <article><small>多因子雷达</small><h2>证据与冲突</h2><p>当前六因子评分仍是过渡实验，未来将区分正式分、观察分和风险扣分。</p></article>
   <article><small>MACD研究</small><h2>规则与失败记录</h2><p>所有成功、失败、不稳定和样本不足的实验永久保留，不只展示有利结果。</p></article>
  </section>
  <details className="rtAboutDetails"><summary>数据、评分与风险说明</summary><div><p><b>数据周期：</b>日线主要观察 20 和 100 个交易日；周线、月线只使用当时已经完成的周期 K 线。</p><p><b>评分含义：</b>分数表示规则证据的组合，不等于买入建议、胜率或预期收益。</p><p><b>研究分段：</b>2000—2024 为开发期，2025 为独立验证期，2026 为前向观察期。</p><p><b>主要风险：</b>样本重叠、市场长期漂移、数据覆盖和成交成本都可能影响结果，必须结合研究页复核。</p></div></details>
 </TrackerShell>
}
