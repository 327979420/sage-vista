"use client";
import { useEffect, useMemo, useState } from "react";

type Frame = {
  macd: string;
  macd_score: number;
  macd_histogram: number;
  zero_zone: string;
  bars_since_cross: number | null;
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
  chain_score: number;
  chain_reason: string;
  combined_score: number;
  rsi_divergence_frames: string[];
  volume: {
    label: string;
    score: number;
    ratio: number | null;
    near_bottom: boolean;
    direction: string;
  };
  frames: Record<string, Frame>;
};
type Report = {
  as_of: string;
  universe: { cached: number; eligible: number };
  combined_top10: Item[];
  macd_top10: Item[];
  rsi_top10: Item[];
  volume_top10: Item[];
};
const periods = ["日线", "周线", "月线"];

function PeriodCell({ frame, kind }: { frame: Frame; kind: "macd" | "rsi" }) {
  const hot = kind === "macd" ? frame.macd_score >= 2 : frame.rsi_score >= 2;
  return (
    <div className={`rtPeriod ${hot ? "isHot" : ""}`}>
      <small>{kind === "macd" ? frame.zero_zone : "RSI"}</small>
      <b>{kind === "macd" ? frame.macd : frame.rsi}</b>
      <span>
        {kind === "macd"
          ? `柱 ${frame.macd_histogram}`
          : (frame.rsi_value ?? "—")}
      </span>
    </div>
  );
}

function SignalBoard({
  items,
  kind,
  combined,
}: {
  items: Item[];
  kind: "macd" | "rsi";
  combined: Set<string>;
}) {
  return (
    <div className="rtBoard">
      <div className="rtBoardHead">
        <span>标的</span>
        {periods.map((x) => (
          <span key={x}>{x}</span>
        ))}
        <span>评分</span>
      </div>
      {items.map((item, index) => (
        <article className="rtSignalRow" key={item.symbol}>
          <div className="rtTicker">
            <i>{String(index + 1).padStart(2, "0")}</i>
            <div>
              <b>{item.symbol}</b>
              <small>${item.price}</small>
            </div>
            {combined.has(item.symbol) && <mark>MACD ＋ RSI</mark>}
          </div>
          {periods.map((period) => (
            <PeriodCell key={period} frame={item.frames[period]} kind={kind} />
          ))}
          <div className="rtScore">
            <b>{kind === "macd" ? item.macd_score : item.rsi_score}</b>
            <small>
              {kind === "macd"
                ? `链条 +${item.chain_score}`
                : `${item.rsi_resonance}/3 周期`}
            </small>
          </div>
          {kind === "macd" && <p className="rtReason">{item.chain_reason}</p>}
        </article>
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
  const combined = useMemo(() => {
    if (!data) return new Set<string>();
    return new Set(data.combined_top10.map((x) => x.symbol));
  }, [data]);
  if (!data)
    return (
      <main className="rtPage">
        <div className="rtLoading">正在计算多周期共振…</div>
      </main>
    );
  return (
    <main className="rtPage">
      <header className="rtHero">
        <nav>
          <a href="/zh/watch">← 盯盘助手</a>
          <span>每日收盘后更新</span>
        </nav>
        <div className="rtHeroBody">
          <div>
            <p>INDICATOR TRACKER</p>
            <h1>多周期指标雷达</h1>
            <strong>先看多指标同时确认，再逐项核对信号。</strong>
          </div>
          <div className="rtAsOf">
            <small>数据截至</small>
            <b>{data.as_of}</b>
            <span>本次实际扫描 {data.universe.eligible} 只股票</span>
          </div>
        </div>
      </header>

      <section className="rtSummary">
        <article className="rtSummaryPrimary">
          <small>MACD ＋ RSI 同时满足</small>
          <b>{data.combined_top10.length}</b>
          <p>多周期传导与 RSI 底背离同时出现</p>
        </article>
        <article>
          <small>本次扫描</small>
          <b>{data.universe.eligible}</b>
          <p>通过价格、成交额和历史长度过滤</p>
        </article>
        <article>
          <small>历史数据库</small>
          <b>{data.universe.cached}</b>
          <p>包含活跃与退市样本，供研究使用</p>
        </article>
        <article>
          <small>数据日期</small>
          <b>{data.as_of.slice(5)}</b>
          <p>只使用已完成的美国市场收盘数据</p>
        </article>
      </section>

      <section className="rtStrict rtPriorityOne">
        <div className="rtSectionTitle">
          <div>
            <p>第一优先级 / 双指标确认</p>
            <h2>MACD 与 RSI 同时发出信号</h2>
          </div>
          <span>先从这里开始复核</span>
        </div>
        <div className="rtStrictGrid">
          {data.combined_top10.map((x) => (
            <article key={x.symbol}>
              <header>
                <mark>MACD ＋ RSI</mark>
                <b>{x.symbol}</b>
                <strong>{x.combined_score}分</strong>
              </header>
              <p>{x.chain_reason}</p>
              <footer>
                <span>RSI：{x.rsi_divergence_frames.join("、")}出现底背离</span>
                <span>成交量：{x.volume.label}</span>
              </footer>
            </article>
          ))}
        </div>
      </section>

      <section className="rtSignals">
        <div className="rtSectionTitle">
          <div>
            <p>单项观察 / MACD</p>
            <h2>零轴下优先，观察小周期向大周期传导</h2>
          </div>
          <span>日线 → 周线 → 月线</span>
        </div>
        <SignalBoard items={data.macd_top10} kind="macd" combined={combined} />
      </section>
      <section className="rtSignals">
        <div className="rtSectionTitle">
          <div>
            <p>单项观察 / RSI</p>
            <h2>观察超卖修复和价格底背离</h2>
          </div>
          <span>价格新低，RSI低点抬高</span>
        </div>
        <SignalBoard items={data.rsi_top10} kind="rsi" combined={combined} />
      </section>

      <section className="rtVolume">
        <div className="rtSectionTitle">
          <div>
            <p>独立提醒 / 成交量</p>
            <h2>成交量明显高于近期平均水平</h2>
          </div>
          <span>≥ 20日均量的1.8倍</span>
        </div>
        <div className="rtVolumeGrid">
          {data.volume_top10.map((x, i) => (
            <article
              key={x.symbol}
              className={x.volume.direction === "下跌" ? "isDown" : ""}
            >
              <i>{String(i + 1).padStart(2, "0")}</i>
              <div>
                <b>{x.symbol}</b>
                <small>{x.volume.label}</small>
              </div>
              <strong>{x.volume.ratio ?? "—"}×</strong>
              <span>
                {x.volume.near_bottom ? "底部区域" : "非底部"} ·{" "}
                {x.volume.direction}
              </span>
            </article>
          ))}
        </div>
      </section>

      <footer className="rtDisclaimer">
        <b>阅读顺序：</b>
        先检查“双指标确认”，再看 MACD、RSI
        和成交量的单项证据。入选只表示值得进一步核对，不代表可以立即买入；周线和月线在本周期收盘前仍可能变化。
      </footer>
    </main>
  );
}
