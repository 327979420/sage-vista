"use client";
import { useEffect, useState } from "react";
type Stats = {
  periods: number;
  mean_return?: number;
  win_rate_pct?: number;
  annualized_sharpe?: number;
  max_drawdown?: number;
};
type Combo = Record<
  "baseline" | "sector_neutral" | "sector_and_beta_neutral",
  Stats
> & { exposure_coverage_pct: number };
type Report = {
  coverage_pct: number;
  results: Record<string, Record<string, Combo>>;
  candidates: { combination: string; design: string }[];
};
const comboNames: Record<string, string> = {
  trend_confluence: "趋势共振",
  breakout_confirmation: "突破确认",
  balanced_technical: "均衡技术",
};
const designNames: Record<string, string> = {
  baseline: "原始组合",
  sector_neutral: "行业中性",
  sector_and_beta_neutral: "行业+Beta中性",
};
const splitNames: Record<string, string> = {
  development: "开发期",
  validation: "2025验证",
  forward_test: "2026前瞻",
};
const pct = (x?: number) =>
  x === undefined ? "—" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(2)}%`;
export default function NeutralizationPage() {
  const [data, setData] = useState<Report | null>(null);
  useEffect(() => {
    fetch("/neutralization-test.json")
      .then((x) => x.json())
      .then(setData);
  }, []);
  if (!data) return <main className="watchdash">正在载入中性化测试…</main>;
  return (
    <main className="watchdash">
      <header className="watchhero contextHero">
        <div>
          <a href="/zh">← 返回因子研究</a>
          <p className="label">行业与市场暴露测试</p>
          <h1>把“押中风格”从能力中剥离。</h1>
          <p>历史时点只使用过去252日数据推断行业ETF归属与SPY Beta。</p>
        </div>
        <div className="contextScore">
          <small>暴露覆盖</small>
          <b>{data.coverage_pct}%</b>
          <span>{data.candidates.length}个候选进入显著性检验</span>
        </div>
      </header>
      <section className="watchnote">
        <b>当前结论：</b>
        行业中性的均衡技术组合在三个阶段平均值均为正；但行业+Beta中性版本开发期为负，因此现在不能晋级模拟交易。
      </section>
      {Object.entries(data.results).map(([split, combos]) => (
        <section className="neutralBlock" key={split}>
          <h2>{splitNames[split]}</h2>
          <div className="neutralRow head">
            <span>技术组合</span>
            <span>处理方式</span>
            <span>平均10日</span>
            <span>胜率</span>
            <span>Sharpe</span>
            <span>最大回撤</span>
          </div>
          {Object.entries(combos).flatMap(([combo, designs]) =>
            ["baseline", "sector_neutral", "sector_and_beta_neutral"].map(
              (design) => {
                const s = designs[design as keyof Combo] as Stats;
                return (
                  <div className="neutralRow" key={`${combo}-${design}`}>
                    <b>{comboNames[combo]}</b>
                    <span>{designNames[design]}</span>
                    <strong
                      className={(s.mean_return ?? 0) >= 0 ? "green" : "red"}
                    >
                      {pct(s.mean_return)}
                    </strong>
                    <span>{s.win_rate_pct ?? "—"}%</span>
                    <span>{s.annualized_sharpe ?? "—"}</span>
                    <span className="red">{pct(s.max_drawdown)}</span>
                  </div>
                );
              },
            ),
          )}
        </section>
      ))}
      <section className="zhrules">
        <h2>下一道门槛</h2>
        <p>
          <b>1</b>对行业中性候选做区块Bootstrap，处理月份收益的时间相关性。
        </p>
        <p>
          <b>2</b>逐年滚动检查，不能只靠2025和2026的少数月份。
        </p>
        <p>
          <b>3</b>用正式历史行业分类替换ETF相关性代理后再复验。
        </p>
        <mark>
          行业ETF归属是统计代理，不是公司的真实历史行业标签；Beta对冲也是日线级近似。
        </mark>
      </section>
    </main>
  );
}
