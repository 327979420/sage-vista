import {Localized} from '../../../../i18n/locale';

// Plain-language summary of how the ranking works. Each claim mirrors the
// production rules in docs/rules/04_SCORING.md and 07_RANKING_AND_TRACKING.md.
const steps=[
 {number:"01",term:"Regime filter",title:"方向过滤",body:"月线方向必须获得许可、周线确认，且不处于月线高位区；相对前60日高点已有回调、局部结构完好，价格与成交额达到可交易门槛。"},
 {number:"02",term:"Entry setup",title:"入场形态",body:"三类门票：两底金叉、三推突破、支撑反转。新提名需要当日日线 MACD 金叉；已入选的股票只要原结构没有被收盘跌破，就留在持续观察。"},
 {number:"03",term:"Multi-timeframe score",title:"多周期评分",body:"月、周、日使用同一套因子模板，同类证据封顶以避免重复计分，再按 3∶2∶1 加权。数据覆盖不足 80% 的股票不评分。"},
 {number:"04",term:"Daily re-scoring",title:"跟踪与复评",body:"每个美股交易日收盘后自动复评。上榜后涨跌从提名当日收盘价计算；原提名与历史记录永久保留，不会改写。"},
];
const principles=[
 {title:"时点数据，无未来函数",body:"只使用当时已经完整收盘的 K 线；历史检验按下一交易日开盘价进入。"},
 {title:"样本外验证",body:"2000—2024 年为开发期，2025 年为独立验证期，2026 年为前向观察期。"},
 {title:"分数不等于概率",body:"分数表示复核优先级和证据强弱，不是胜率或预期收益。"},
];

export default function MultiFactorIntro(){
 return <Localized><section className="mfIntro" aria-labelledby="mfIntroTitle">
  <header><small>关于多因子机会</small><h2 id="mfIntroTitle">多周期趋势与动量筛选</h2><p>先用月线和周线确认方向，再在日线上寻找回调后的入场形态，最后按证据强弱排序，帮你把注意力放在最值得研究的股票上。</p></header>
  <ol className="mfIntroSteps">{steps.map(s=><li key={s.number}><span>{s.number}</span><small lang="en">{s.term}</small><h3>{s.title}</h3><p>{s.body}</p></li>)}</ol>
  <div className="mfIntroPrinciples">{principles.map(p=><div key={p.title}><b>{p.title}</b><p>{p.body}</p></div>)}</div>
  <p className="mfIntroNote">研究工具，不构成投资建议。股票来自 SV 的观察池，不代表整个美股市场；候选不等于买入，是否交易仍需你自己判断。</p>
 </section></Localized>;
}
