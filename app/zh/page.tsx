"use client";
import { useEffect, useMemo, useState } from "react";
type Metric = {
  factor: string;
  horizon: number;
  mean_ic: number | null;
  ic_positive_pct: number | null;
  spread: number | null;
};
type Combo = {
  combination: string;
  mean_ic: number | null;
  spread: number | null;
  dates: number;
};
type Run = {
  test_year: number;
  training_window: string;
  selected_combination: string;
  test_ic: number | null;
  test_dates: number;
};
type Report = {
  generated_at: string;
  sample: {
    loaded: number;
    eligible_active: number;
    eligible_delisted: number;
    stock_months: number;
    dates: number;
    start: string;
    end: string;
  };
  split_metrics: Record<string, Metric[]>;
  combinations: Record<string, Combo[]>;
  regime_metrics: Record<string, Metric[]>;
  rolling_oos: {
    summary: {
      years: number;
      positive_ic_years: number;
      positive_ic_pct: number;
      median_test_ic: number;
      worst_test_ic: number;
      abstained_years: number;
      low_sample_years_excluded: number;
    };
    runs: Run[];
  };
  limitations: string[];
};
const factorNames: Record<string, string> = {
  breakout_252: "接近52周新高",
  low_volatility: "低波动",
  volatility_contraction: "波动收缩",
  momentum_3_1: "3个月动量",
  momentum_12_1: "12个月动量（跳过最近1月）",
  volume_expansion: "成交量放大",
  rsi_14: "RSI强度",
  trend_quality: "均线趋势质量",
  relative_strength_6m: "相对大盘强度",
  liquidity: "流动性",
  macd_strength: "MACD强度",
  adx_14: "ADX趋势强度",
  momentum_6_1: "6个月动量",
};
const comboNames: Record<string, string> = {
  balanced_technical: "均衡技术组合",
  breakout_confirmation: "突破确认组合",
  trend_confluence: "趋势共振组合",
};
const pct = (x: number | null) =>
  x === null ? "—" : `${(x * 100).toFixed(2)}%`;
export default function ChineseResearch() {
  const [data, setData] = useState<Report | null>(null);
  useEffect(() => {
    fetch("/eodhd-factor-validation.json")
      .then((x) => x.json())
      .then(setData);
  }, []);
  const regimes = useMemo(() => {
    if (!data) return { on: [], off: [] };
    const pick = (key: string) =>
      data.regime_metrics[key]
        .filter((x) => x.horizon === 10 && x.mean_ic !== null)
        .sort((a, b) => (b.mean_ic ?? -9) - (a.mean_ic ?? -9))
        .slice(0, 6);
    return { on: pick("risk_on"), off: pick("risk_off") };
  }, [data]);
  if (!data) return <main className="zhdash">正在载入因子研究结果…</main>;
  const roll = data.rolling_oos.summary;
  return (
    <main className="zhdash">
      <header className="zhhero">
        <div>
          <p className="label">NORTHSTAR / 中文因子研究</p>
          <h1>
            我们在验证规则，
            <br />
            不是推荐股票。
          </h1>
          <p>当前阶段：历史回测与滚动样本外验证</p>
          <a className="watchlink" href="/zh/watch">
            打开中文行业盯盘助手 →
          </a>
          <a className="watchlink secondary" href="/zh/context">
            查看ETF环境因子训练 →
          </a>
        </div>
        <aside>
          <small>载入历史</small>
          <b>{data.sample.loaded}</b>
          <span>只股票</span>
          <small>股票月份</small>
          <b>{data.sample.stock_months.toLocaleString()}</b>
          <span>条观察</span>
        </aside>
      </header>
      <section className="zhnotice">
        <b>现在不能用于真实下单。</b>{" "}
        页面中的数值用于判断一个因子是否长期有效、是否只在特定市场环境有效，以及是否值得进入下一轮模拟测试。
      </section>
      <section className="zhprogress">
        <article>
          <small>01 · 已完成</small>
          <h2>数据与偏差控制</h2>
          <p>
            加入活跃股和退市股；先过滤低价、低流动性和高点差股票；收盘信号按次日开盘计算。
          </p>
        </article>
        <article>
          <small>02 · 正在进行</small>
          <h2>因子稳定性</h2>
          <p>
            逐个检查13个因子，再检查3个预先定义的组合，比较不同年份和市场环境。
          </p>
        </article>
        <article>
          <small>03 · 尚未开始</small>
          <h2>前向模拟</h2>
          <p>
            只有通过稳定性门槛后，才每日生成模拟信号；在此之前不提供买卖建议。
          </p>
        </article>
      </section>
      <section className="zhresearchgrid">
        <article>
          <p className="label">滚动样本外测试</p>
          <h2>
            {roll.positive_ic_years}/{roll.years} 个有效年份方向为正
          </h2>
          <div className="bigmetric">{roll.positive_ic_pct}%</div>
          <p>
            每次只使用过去5年选择一个已有组合，然后测试下一年。中位测试IC为{" "}
            {roll.median_test_ic.toFixed(3)}，最差年份为{" "}
            {roll.worst_test_ic.toFixed(3)}。
          </p>
          <mark>
            这说明存在一定信号，但稳定性还不够。正相关年份不等于每年盈利，也不能据此实盘。
          </mark>
        </article>
        <article>
          <p className="label">最近年度轨迹</p>
          {data.rolling_oos.runs
            .slice(-8)
            .reverse()
            .map((x) => (
              <div className="yearrow" key={x.test_year}>
                <b>{x.test_year}</b>
                <span>{comboNames[x.selected_combination] ?? "不交易"}</span>
                <strong className={(x.test_ic ?? 0) > 0 ? "green" : "red"}>
                  {x.test_ic === null ? "跳过" : x.test_ic.toFixed(3)}
                </strong>
                <small>{x.test_dates}个月</small>
              </div>
            ))}
        </article>
      </section>
      <section className="zhresearchgrid">
        <article>
          <p className="label">风险偏好环境 · 10日</p>
          <h2>较强的单因子</h2>
          <div className="factorhead">
            <span>因子</span>
            <span>IC</span>
            <span>多空差</span>
          </div>
          {regimes.on.map((x) => (
            <div className="factorline" key={x.factor}>
              <b>{factorNames[x.factor] ?? x.factor}</b>
              <span>{x.mean_ic?.toFixed(3)}</span>
              <span>{pct(x.spread)}</span>
            </div>
          ))}
        </article>
        <article>
          <p className="label">风险规避环境 · 10日</p>
          <h2>因子会发生变化</h2>
          <div className="factorhead">
            <span>因子</span>
            <span>IC</span>
            <span>多空差</span>
          </div>
          {regimes.off.map((x) => (
            <div className="factorline" key={x.factor}>
              <b>{factorNames[x.factor] ?? x.factor}</b>
              <span>{x.mean_ic?.toFixed(3)}</span>
              <span>{pct(x.spread)}</span>
            </div>
          ))}
        </article>
      </section>
      <section className="zhrules">
        <h2>接下来继续训练什么</h2>
        <p>
          <b>1</b>扩大到更完整的活跃股与退市股历史，而不是只依赖1,000只抽样。
        </p>
        <p>
          <b>2</b>
          取得可靠的历史行业分类后，做行业中性化，避免误把科技板块上涨当成模型能力。
        </p>
        <p>
          <b>3</b>
          按年份、市场环境和未来可获得的规模分组，删除方向经常反转的因子。
        </p>
        <p>
          <b>4</b>
          对留下的因子测试交易成本、换手率、最大回撤和相关性，再决定权重。
        </p>
        <p>
          <b>5</b>通过门槛后进入只记录、不下单的前向模拟。
        </p>
        <mark>
          IC可以简单理解为“因子排名与未来收益排名的一致程度”。接近0代表没有稳定关系；正值不代表一定赚钱，还必须同时检查成本、回撤和样本外稳定性。
        </mark>
      </section>
    </main>
  );
}
