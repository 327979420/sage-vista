"use client";
import { useEffect, useState } from "react";
type Frame = {
  macd: string;
  macd_score: number;
  macd_histogram: number;
  rsi: string;
  rsi_score: number;
  rsi_value: number | null;
};
type Item = {
  symbol: string;
  price: number;
  macd_score: number;
  rsi_score: number;
  macd_resonance: number;
  rsi_resonance: number;
  frames: Record<string, Frame>;
};
type Report = {
  as_of: string;
  intraday: { available: boolean; reason: string; required: string };
  universe: { eligible: number; filters: string };
  macd_top10: Item[];
  rsi_top10: Item[];
};
const frameNames = ["日线", "周线", "月线"];
function SignalTable({ items, kind }: { items: Item[]; kind: "macd" | "rsi" }) {
  return (
    <div className="resonanceTable">
      <div className="resonanceRow head">
        <span>股票</span>
        <span>日线</span>
        <span>周线</span>
        <span>月线</span>
        <span>共振</span>
      </div>
      {items.map((x, i) => (
        <div className="resonanceRow" key={x.symbol}>
          <b>
            <i>{i + 1}</i>
            {x.symbol}
            <small>${x.price}</small>
          </b>
          {frameNames.map((f) => (
            <span
              key={f}
              className={
                (kind === "macd"
                  ? x.frames[f].macd_score
                  : x.frames[f].rsi_score) >= 2
                  ? "signalHot"
                  : ""
              }
            >
              <strong>
                {kind === "macd" ? x.frames[f].macd : x.frames[f].rsi}
              </strong>
              <small>
                {kind === "macd"
                  ? `柱 ${x.frames[f].macd_histogram}`
                  : `RSI ${x.frames[f].rsi_value ?? "—"}`}
              </small>
            </span>
          ))}
          <em>
            {kind === "macd" ? x.macd_score : x.rsi_score}分
            <small>
              {kind === "macd" ? x.macd_resonance : x.rsi_resonance}/3周期
            </small>
          </em>
        </div>
      ))}
    </div>
  );
}
export default function ResonanceTracker() {
  const [data, setData] = useState<Report | null>(null);
  useEffect(() => {
    fetch("/resonance-tracker.json")
      .then((x) => x.json())
      .then(setData);
  }, []);
  if (!data) return <main className="watchdash">正在载入多周期共振…</main>;
  return (
    <main className="watchdash">
      <header className="watchhero contextHero">
        <div>
          <a href="/zh/watch">← 返回盯盘助手</a>
          <p className="label">MACD / RSI 多周期 Tracker</p>
          <h1>寻找从小周期向大周期传导的拐点。</h1>
          <p>
            截至美国市场 {data.as_of} 已完成收盘 · 扫描{data.universe.eligible}
            只合格股票
          </p>
        </div>
        <div className="contextScore">
          <small>当前可用周期</small>
          <b>3/4</b>
          <span>日线 · 周线 · 月线</span>
        </div>
      </header>
      <section className="intradayNotice">
        <b>4小时数据尚未接通</b>
        <p>
          当前订阅访问1小时接口返回403，所以页面不会伪造4小时信号。升级到 EOD +
          Intraday All World Extended
          或接入实时WebSocket后，可启用完整4小时→日线→周线→月线链条。
        </p>
      </section>
      <section className="trackerIntro">
        <article>
          <small>MACD榜首</small>
          <b>{data.macd_top10[0]?.symbol ?? "—"}</b>
          <span>{data.macd_top10[0]?.macd_score ?? 0}分</span>
        </article>
        <article>
          <small>RSI榜首</small>
          <b>{data.rsi_top10[0]?.symbol ?? "—"}</b>
          <span>{data.rsi_top10[0]?.rsi_score ?? 0}分</span>
        </article>
        <article>
          <small>过滤条件</small>
          <p>股价≥$5，最新成交额≥$10m；只使用研究样本中仍在交易的股票。</p>
        </article>
      </section>
      <section className="trackerSection">
        <p className="label">TOP 10 · MACD 共振</p>
        <h2>金叉、准备金叉与向上拐头</h2>
        <SignalTable items={data.macd_top10} kind="macd" />
      </section>
      <section className="trackerSection">
        <p className="label">TOP 10 · RSI 共振</p>
        <h2>超卖、超卖修复与底背离</h2>
        <SignalTable items={data.rsi_top10} kind="rsi" />
      </section>
      <section className="zhrules">
        <h2>怎样使用</h2>
        <p>
          <b>1</b>共振只代表多个周期出现相同方向，不自动等于买点。
        </p>
        <p>
          <b>2</b>周线和月线是正在形成的K线，周期结束前信号可能消失。
        </p>
        <p>
          <b>3</b>下一步仍需检查价格结构、成交量、止损位置和收益风险比。
        </p>
        <mark>
          Tracker 是候选发现工具，不提供自动下单，也不能替代盘中实时行情确认。
        </mark>
      </section>
    </main>
  );
}
