"use client";
import { useEffect, useState } from "react";
type Candidate = {
  ticker: string;
  name: string;
  as_of: string;
  status: string;
  score: number;
  confirmations: number;
  price: number;
  entry_trigger: number;
  stop: number;
  target: number;
  reward_risk: number;
  max_holding_days: number;
  shares: number;
  position_value: number;
  position_pct: number;
  factors: Record<string, number>;
  instruction: string;
};
type Report = {
  as_of: string;
  market_regime: string;
  universe: { sampled: number; eligible: number };
  account_assumption: number;
  candidates: Candidate[];
  rules: string[];
};
const money = (x: number) =>
  `$${x.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
export default function ChineseInsights() {
  const [data, setData] = useState<Report | null>(null);
  useEffect(() => {
    fetch("/trade-insights.json")
      .then((x) => x.json())
      .then(setData);
  }, []);
  if (!data) return <main className="zhdash">正在载入最新研究数据…</main>;
  return (
    <main className="zhdash">
      <header className="zhhero">
        <div>
          <p className="label">NORTHSTAR / 中文交易洞察</p>
          <h1>
            先告诉你该看什么，
            <br />
            再解释为什么。
          </h1>
          <p>
            数据日期 {data.as_of} · 市场环境：<b>{data.market_regime}</b>
          </p>
        </div>
        <aside>
          <small>本次扫描</small>
          <b>{data.universe.sampled}</b>
          <span>只股票</span>
          <small>通过基础筛选</small>
          <b>{data.universe.eligible}</b>
          <span>只股票</span>
        </aside>
      </header>
      <section className="zhnotice">
        <b>如何使用：</b>
        “等待”不是买入。只有价格突破入场触发价，并且大盘环境没有转坏时，才进入下一步判断。
      </section>
      <section className="zhcards">
        {data.candidates.map((x, i) => (
          <article className="zhcard" key={x.ticker}>
            <div className="zhcardtop">
              <div>
                <small>
                  #{i + 1} · {x.status}
                </small>
                <h2>
                  {x.ticker} <span>{x.name}</span>
                </h2>
              </div>
              <strong>
                {x.score}
                <small>/100</small>
              </strong>
            </div>
            <p>{x.instruction}</p>
            <div className="tradelevels">
              <div>
                <small>入场触发</small>
                <b>{money(x.entry_trigger)}</b>
              </div>
              <div>
                <small>止损</small>
                <b className="red">{money(x.stop)}</b>
              </div>
              <div>
                <small>目标</small>
                <b className="green">{money(x.target)}</b>
              </div>
              <div>
                <small>最长持有</small>
                <b>{x.max_holding_days} 日</b>
              </div>
            </div>
            <div className="zhsize">
              <span>以 {money(data.account_assumption)} 账户举例</span>
              <b>
                {x.shares} 股 · 约 {money(x.position_value)} · {x.position_pct}%
                仓位
              </b>
            </div>
            <details>
              <summary>
                为什么进入观察名单？（{x.confirmations}/4 项确认）
              </summary>
              {Object.entries(x.factors).map(([k, v]) => (
                <div className="zhfactor" key={k}>
                  <span>{k}</span>
                  <b>{v}</b>
                </div>
              ))}
            </details>
          </article>
        ))}
      </section>
      <section className="zhrules">
        <h2>这套页面目前能做什么</h2>
        {data.rules.map((x, i) => (
          <p key={x}>
            <b>{i + 1}</b>
            {x}
          </p>
        ))}
        <mark>
          重要：目前缺少实时期权墙、盘中报价和完整历史行业分类，因此这里先用于收盘后的交易准备，不用于自动下单。
        </mark>
      </section>
    </main>
  );
}
