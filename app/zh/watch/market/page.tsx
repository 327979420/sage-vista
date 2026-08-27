"use client";
import { useEffect, useState } from "react";
type Fund = {
  ticker: string;
  name: string;
  role: string;
  price: number;
  return_1d: number;
  return_5d: number;
  return_20d: number;
  above_ema20: boolean;
  above_ema50: boolean;
};
type Report = {
  as_of: string;
  market_temperature: {
    score: number;
    max_score: number;
    state: string;
    explanation: string;
  };
  ratios: Record<string, number>;
  funds: Fund[];
  interpretation: string[];
};
const pct = (x: number) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(2)}%`;
export default function MarketETFWatch() {
  const [data, setData] = useState<Report | null>(null);
  useEffect(() => {
    fetch("/market-etf-watch.json", { cache: "no-store" })
      .then((x) => x.json())
      .then(setData);
  }, []);
  if (!data) return <main className="watchdash">正在载入市场ETF数据…</main>;
  return (
    <main className="watchdash">
      <header className="watchhero">
        <div>
          <a href="/zh/watch">← 返回行业雷达</a>
          <p className="label">中文盯盘助手 / 市场ETF温度计</p>
          <h1>市场情绪、价值与动量</h1>
          <p>
            数据日期 {data.as_of} · 当前状态：
            <b>{data.market_temperature.state}</b>
          </p>
        </div>
        <div className="temperature">
          <span>市场温度</span>
          <b>
            {data.market_temperature.score}/{data.market_temperature.max_score}
          </b>
          <i>
            <em
              style={{
                width: `${(data.market_temperature.score / data.market_temperature.max_score) * 100}%`,
              }}
            />
          </i>
          <small>{data.market_temperature.explanation}</small>
        </div>
      </header>
      <section className="ratioCards">
        {Object.entries(data.ratios).map(([name, value]) => (
          <article key={name}>
            <small>{name}</small>
            <b className={value >= 0 ? "green" : "red"}>{pct(value)}</b>
            <span>过去20个交易日</span>
          </article>
        ))}
      </section>
      <section className="sectortable">
        <div className="fundrow head">
          <span>基金/ETF</span>
          <span>代表含义</span>
          <span>1日</span>
          <span>5日</span>
          <span>20日</span>
          <span>EMA20</span>
          <span>EMA50</span>
        </div>
        {data.funds.map((x) => (
          <div className="fundrow" key={x.ticker}>
            <b>
              {x.ticker}
              <small>{x.name}</small>
            </b>
            <span>{x.role}</span>
            <span className={x.return_1d >= 0 ? "green" : "red"}>
              {pct(x.return_1d)}
            </span>
            <span className={x.return_5d >= 0 ? "green" : "red"}>
              {pct(x.return_5d)}
            </span>
            <span className={x.return_20d >= 0 ? "green" : "red"}>
              {pct(x.return_20d)}
            </span>
            <span>{x.above_ema20 ? "上方" : "下方"}</span>
            <span>{x.above_ema50 ? "上方" : "下方"}</span>
          </div>
        ))}
      </section>
      <section className="zhrules">
        <h2>怎样理解这些数据</h2>
        {data.interpretation.map((x, i) => (
          <p key={x}>
            <b>{i + 1}</b>
            {x}
          </p>
        ))}
        <mark>
          注意：DJI是指数，不是基金；页面使用DIA作为道琼斯工业平均指数的可交易代理。类似地，这里研究的是ETF价格关系，不等于基金经理的实际持仓观点。
        </mark>
      </section>
    </main>
  );
}
