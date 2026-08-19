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
  continuous_results: ContinuousResult[];
};
type Relation = {
  dates: number;
  spearman: number | null;
  ci_95: [number | null, number | null];
  p_one_sided: number | null;
};
type ContinuousResult = {
  gate: string;
  pair: string;
  lookback: number;
  combination: string;
  splits: Record<"development" | "validation" | "forward_test", Relation>;
  development_q_bh: number;
  verdict: "candidate_for_more_testing" | "not_confirmed";
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
  const continuous = useMemo(
    () =>
      [...(data?.continuous_results ?? [])].sort(
        (a, b) =>
          (b.splits.development.spearman ?? -9) -
          (a.splits.development.spearman ?? -9),
      ),
    [data],
  );
  if (!data) return <main className="watchdash">正在载入环境因子测试…</main>;
  const passed = continuous.filter(
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
          <p>检验ETF相对强弱越明显，技术组合的10日表现是否越强。</p>
        </div>
        <div className="contextScore">
          <small>通过严格门槛</small>
          <b>
            {passed}/{continuous.length}
          </b>
          <span>当前不提升任何因子权重</span>
        </div>
      </header>
      <section className="watchnote">
        <b>连续强度结论：</b>
        目前没有环境因子获得升级资格。开发期最强关系也未通过95%置信区间和
        {continuous.length}项多重检验修正，且后续阶段并不稳定。
      </section>
      <section className="contextExplain">
        <article>
          <small>环境强度</small>
          <h2>6组ETF × 3个窗口</h2>
          <p>预先登记20、60和120日窗口，没有看结果后临时增加参数。</p>
        </article>
        <article>
          <small>技术信号</small>
          <h2>3个预先定义组合</h2>
          <p>趋势共振、突破确认、均衡技术；没有看完结果再临时改配方。</p>
        </article>
        <article>
          <small>统计保护</small>
          <h2>2,000次重复抽样</h2>
          <p>选择技术得分前20%，扣除20个基点成本，再与同期合格股票比较。</p>
        </article>
      </section>
      <section className="sectortable contextTable">
        <div className="contextRow head">
          <span>环境</span>
          <span>技术组合</span>
          <span>开发期相关</span>
          <span>95%区间</span>
          <span>修正后q值</span>
          <span>2025 / 2026</span>
          <span>结论</span>
        </div>
        {continuous.slice(0, 18).map((x) => (
          <div
            className="contextRow"
            key={`${x.gate}-${x.lookback}-${x.combination}`}
          >
            <b>
              {gateNames[x.gate]}
              <small>
                {x.pair} · {x.lookback}日
              </small>
            </b>
            <span>{comboNames[x.combination]}</span>
            <span
              className={
                (x.splits.development.spearman ?? 0) >= 0 ? "green" : "red"
              }
            >
              {x.splits.development.spearman?.toFixed(3) ?? "—"}
              <small>{x.splits.development.dates}个月</small>
            </span>
            <span>
              {x.splits.development.ci_95[0]?.toFixed(3) ?? "—"} ～{" "}
              {x.splits.development.ci_95[1]?.toFixed(3) ?? "—"}
            </span>
            <span>{x.development_q_bh.toFixed(3)}</span>
            <span>
              {x.splits.validation.spearman?.toFixed(3) ?? "—"} /{" "}
              {x.splits.forward_test.spearman?.toFixed(3) ?? "—"}
              <small>
                {x.splits.validation.dates} / {x.splits.forward_test.dates}个月
              </small>
            </span>
            <strong
              className={`verdict ${x.verdict === "not_confirmed" ? "not_stable" : x.verdict}`}
            >
              {x.verdict === "candidate_for_more_testing"
                ? "进入下一轮"
                : "尚未确认"}
            </strong>
          </div>
        ))}
      </section>
      <p className="contextFootnote">
        表格显示开发期相关性最高的18项；统计修正和晋级判断使用全部
        {continuous.length}项，没有隐藏较差结果。
      </p>
      <section className="zhrules">
        <h2>本轮完成后，下一步怎么训练</h2>
        <p>
          <b>1</b>
          继续积累前瞻月份；上一轮有{close.length}
          个二元组合方向一致，但本轮连续强度没有确认它们，因此仍不加权。
        </p>
        <p>
          <b>2</b>
          20、60和120日窗口已经完成；下一轮加入行业中性化与市场Beta中性化。
        </p>
        <p>
          <b>3</b>
          开始行业中性化和市场Beta中性化，判断结果是否只是科技股或大盘上涨带来的假象。
        </p>
        <mark>
          这页是研究记录，不是买卖建议。0个通过不是坏结果，它阻止模型把短期巧合误当成规律。
        </mark>
      </section>
    </main>
  );
}
