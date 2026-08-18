"use client";
import { useEffect, useMemo, useState } from "react";

type Verdict = {
  gate: string;
  pair: string;
  combination: string;
  development_uplift: number;
  validation_enabled_mean: number | null;
  forward_enabled_mean: number | null;
  validation_dates: number;
  forward_dates: number;
  verdict:
    "candidate_for_more_testing" | "insufficient_evidence" | "not_stable";
};
type Report = {
  generated_at: string;
  design: Record<string, string>;
  verdicts: Verdict[];
};
const gateNames: Record<string, string> = {
  growth: "成长风格",
  small_cap: "小盘风险偏好",
  breadth: "市场宽度",
  credit: "信用风险偏好",
  value: "价值风格",
  momentum: "动量风格",
};
const comboNames: Record<string, string> = {
  balanced_technical: "均衡技术组合",
  breakout_confirmation: "突破确认组合",
  trend_confluence: "趋势共振组合",
};
const verdictText = {
  candidate_for_more_testing: "进入下一轮",
  insufficient_evidence: "方向一致，证据不足",
  not_stable: "方向不稳定",
};
const pct = (x: number | null) =>
  x === null ? "—" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(2)}%`;

export default function ContextFactorResearch() {
  const [data, setData] = useState<Report | null>(null);
  useEffect(() => {
    fetch("/market-context-factor-test.json")
      .then((x) => x.json())
      .then(setData);
  }, []);
  const rows = useMemo(
    () =>
      [...(data?.verdicts ?? [])].sort(
        (a, b) => b.development_uplift - a.development_uplift,
      ),
    [data],
  );
  if (!data) return <main className="watchdash">正在载入环境因子测试…</main>;
  const passed = rows.filter(
    (x) => x.verdict === "candidate_for_more_testing",
  ).length;
  const close = rows.filter((x) => x.verdict === "insufficient_evidence");
  return (
    <main className="watchdash">
      <header className="watchhero contextHero">
        <div>
          <a href="/zh">← 返回因子研究</a>
          <p className="label">下一轮训练 / ETF市场环境 × 技术因子</p>
          <h1>什么环境更适合什么信号？</h1>
          <p>先用ETF关系判断环境，再检查技术组合的10日表现。</p>
        </div>
        <div className="contextScore">
          <small>通过严格门槛</small>
          <b>{passed}/18</b>
          <span>当前不提升任何因子权重</span>
        </div>
      </header>
      <section className="watchnote">
        <b>结论：</b>目前没有环境因子获得升级资格。{close.length}{" "}
        个组合在三个阶段方向一致，
        但有效月份不足，只能保留观察，不能用于真实交易。
      </section>
      <section className="contextExplain">
        <article>
          <small>环境开关</small>
          <h2>6组主流ETF关系</h2>
          <p>QQQ/SPY、IWM/SPY、RSP/SPY、HYG/LQD、IWD/IWF、MTUM/SPY。</p>
        </article>
        <article>
          <small>技术信号</small>
          <h2>3个预先定义组合</h2>
          <p>趋势共振、突破确认、均衡技术；没有看完结果再临时改配方。</p>
        </article>
        <article>
          <small>交易假设</small>
          <h2>次日开盘，持有10日</h2>
          <p>选择技术得分前20%，扣除20个基点成本，再与同期合格股票比较。</p>
        </article>
      </section>
      <section className="sectortable contextTable">
        <div className="contextRow head">
          <span>环境</span>
          <span>技术组合</span>
          <span>开发期提升</span>
          <span>2025净表现</span>
          <span>2026净表现</span>
          <span>结论</span>
        </div>
        {rows.map((x) => (
          <div className="contextRow" key={`${x.gate}-${x.combination}`}>
            <b>
              {gateNames[x.gate]}
              <small>{x.pair} · 20日</small>
            </b>
            <span>{comboNames[x.combination]}</span>
            <span className={x.development_uplift >= 0 ? "green" : "red"}>
              {pct(x.development_uplift)}
            </span>
            <span
              className={
                (x.validation_enabled_mean ?? 0) >= 0 ? "green" : "red"
              }
            >
              {pct(x.validation_enabled_mean)}
              <small>{x.validation_dates}个月</small>
            </span>
            <span
              className={(x.forward_enabled_mean ?? 0) >= 0 ? "green" : "red"}
            >
              {pct(x.forward_enabled_mean)}
              <small>{x.forward_dates}个月</small>
            </span>
            <strong className={`verdict ${x.verdict}`}>
              {verdictText[x.verdict]}
            </strong>
          </div>
        ))}
      </section>
      <section className="zhrules">
        <h2>下一轮怎么训练</h2>
        <p>
          <b>1</b>
          继续积累前瞻月份；“方向一致，证据不足”的组合不加权，只列入候选观察。
        </p>
        <p>
          <b>2</b>
          把简单的开/关条件升级为连续强度，检验ETF相对强弱越大是否真的对应更强回报。
        </p>
        <p>
          <b>3</b>
          加入置信区间、重复抽样和多重检验修正，降低18次测试中偶然撞对的概率。
        </p>
        <mark>
          这页是研究记录，不是买卖建议。0个通过不是坏结果，它阻止模型把短期巧合误当成规律。
        </mark>
      </section>
    </main>
  );
}
