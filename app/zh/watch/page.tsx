"use client";
import { useEffect, useState } from "react";
type News = {
  date: string;
  title: string;
  link: string;
  sentiment?: { polarity: number };
};
type Sector = {
  ticker: string;
  sector: string;
  state: string;
  score: number;
  return_1d: number;
  return_5d: number;
  return_20d: number;
  relative_20d: number;
  above_ema20: boolean;
  above_ema50: boolean;
  volume_ratio: number;
  news: News[];
};
type Report = {
  as_of: string;
  market: {
    spy_price: number;
    spy_20d: number;
    sector_breadth_above_ema50: number;
    sector_count: number;
    state: string;
  };
  sectors: Sector[];
  rules: string[];
};
const pct = (x: number) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(2)}%`;
const tone = (x: number) =>
  x > 0.15 ? "偏正面" : x < -0.15 ? "偏负面" : "中性";
export default function SectorWatch() {
  const [data, setData] = useState<Report | null>(null);
  useEffect(() => {
    fetch("/sector-watch.json")
      .then((x) => x.json())
      .then(setData);
  }, []);
  if (!data) return <main className="watchdash">正在载入行业监控…</main>;
  return (
    <main className="watchdash">
      <header className="watchhero">
        <div>
          <a href="/zh">← 返回因子研究</a>
          <p className="label">中文盯盘助手 / 收盘后版本</p>
          <h1>行业轮动与消息雷达</h1>
          <p>
            数据日期 {data.as_of} · 市场结构：<b>{data.market.state}</b>
          </p>
          <a className="watchlink" href="/zh/watch/market">
            查看主流ETF市场温度计 →
          </a>
        </div>
        <div className="watchpulse">
          <small>SPY 20日</small>
          <b>{pct(data.market.spy_20d)}</b>
          <small>站上50日均线行业</small>
          <b>
            {data.market.sector_breadth_above_ema50}/{data.market.sector_count}
          </b>
        </div>
      </header>
      <section className="watchnote">
        <b>助手职责：</b>
        告诉你资金正在流向哪里、哪些行业正在转弱、发生了什么新闻。它不负责给出买入指令，因子模型仍在独立训练。
      </section>
      <section className="sectortable">
        <div className="sectorrow head">
          <span>行业</span>
          <span>状态</span>
          <span>1日</span>
          <span>5日</span>
          <span>20日</span>
          <span>相对SPY</span>
          <span>成交量</span>
        </div>
        {data.sectors.map((x) => (
          <div className="sectorrow" key={x.ticker}>
            <b>
              {x.sector}
              <small>{x.ticker}</small>
            </b>
            <span className={`state ${x.state}`}>
              {x.state} · {x.score}/5
            </span>
            <span className={x.return_1d >= 0 ? "green" : "red"}>
              {pct(x.return_1d)}
            </span>
            <span className={x.return_5d >= 0 ? "green" : "red"}>
              {pct(x.return_5d)}
            </span>
            <span className={x.return_20d >= 0 ? "green" : "red"}>
              {pct(x.return_20d)}
            </span>
            <span className={x.relative_20d >= 0 ? "green" : "red"}>
              {pct(x.relative_20d)}
            </span>
            <span>{x.volume_ratio.toFixed(2)}×</span>
          </div>
        ))}
      </section>
      <section className="newsgrid">
        {data.sectors.slice(0, 6).map((x) => (
          <article key={x.ticker}>
            <header>
              <div>
                <small>{x.ticker}</small>
                <h2>{x.sector}行业消息</h2>
              </div>
              <b>{x.state}</b>
            </header>
            <p className="sectorread">
              20日涨跌 {pct(x.return_20d)}，相对SPY {pct(x.relative_20d)}；价格
              {x.above_ema50 ? "站在" : "跌破"}50日均线。
            </p>
            {x.news.map((n) => (
              <a href={n.link} target="_blank" rel="noreferrer" key={n.link}>
                <span>
                  {n.date?.slice(0, 10)} · {tone(n.sentiment?.polarity ?? 0)}
                </span>
                <b dangerouslySetInnerHTML={{ __html: n.title }} />
              </a>
            ))}
          </article>
        ))}
      </section>
      <section className="zhrules">
        <h2>提醒规则</h2>
        {data.rules.map((x, i) => (
          <p key={x}>
            <b>{i + 1}</b>
            {x}
          </p>
        ))}
        <mark>
          下一阶段可升级为盘中助手：需要接入实时或延迟分钟行情，并明确刷新频率、提醒阈值和你实际关注的股票列表。
        </mark>
      </section>
    </main>
  );
}
