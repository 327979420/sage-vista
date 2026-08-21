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
  universe: { eligible: number };
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
  overlap,
}: {
  items: Item[];
  kind: "macd" | "rsi";
  overlap: Set<string>;
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
            {overlap.has(item.symbol) && <mark>MACD × RSI</mark>}
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
  const overlap = useMemo(() => {
    if (!data) return new Set<string>();
    const rsi = new Set(data.rsi_top10.map((x) => x.symbol));
    return new Set(
      data.macd_top10.map((x) => x.symbol).filter((x) => rsi.has(x)),
    );
  }, [data]);
  if (!data)
    return (
      <main className="rtPage">
        <div className="rtLoading">正在计算多周期共振…</div>
      </main>
    );
  const overlapItems = data.macd_top10.filter((x) => overlap.has(x.symbol));
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
            <h1>多周期信号雷达</h1>
            <strong>先看指标交集，再看单项排名。</strong>
          </div>
          <div className="rtAsOf">
            <small>数据截至</small>
            <b>{data.as_of}</b>
            <span>{data.universe.eligible} 只流动性合格股票</span>
          </div>
        </div>
      </header>

      <section className="rtSummary">
        <article className="rtSummaryPrimary">
          <small>MACD × RSI 榜单交集</small>
          <b>{overlapItems.length}</b>
          <p>同时进入两个 TOP 10 的股票</p>
        </article>
        <article>
          <small>MACD 榜首</small>
          <b>{data.macd_top10[0]?.symbol ?? "—"}</b>
          <p>{data.macd_top10[0]?.macd_score ?? 0} 分</p>
        </article>
        <article>
          <small>RSI 榜首</small>
          <b>{data.rsi_top10[0]?.symbol ?? "—"}</b>
          <p>{data.rsi_top10[0]?.rsi_score ?? 0} 分</p>
        </article>
        <article>
          <small>严格双因子</small>
          <b>{data.combined_top10.length}</b>
          <p>MACD传导 + RSI底背离</p>
        </article>
      </section>

      <section className="rtFocus">
        <div className="rtSectionTitle">
          <div>
            <p>01 / 最值得先看</p>
            <h2>MACD 与 RSI 榜单交集</h2>
          </div>
          <span>两个独立指标同时选中</span>
        </div>
        {overlapItems.length ? (
          <div className="rtIntersection">
            {overlapItems.map((x) => (
              <article key={x.symbol}>
                <div className="rtIntersectionTicker">
                  <mark>双指标共振</mark>
                  <b>{x.symbol}</b>
                  <span>${x.price}</span>
                </div>
                <div>
                  <small>MACD</small>
                  <strong>{x.macd_score} 分</strong>
                  <p>{x.chain_reason}</p>
                </div>
                <div>
                  <small>RSI</small>
                  <strong>{x.rsi_score} 分</strong>
                  <p>
                    {x.rsi_divergence_frames.length
                      ? `${x.rsi_divergence_frames.join("、")}底背离`
                      : "多周期 RSI 入选"}
                  </p>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="rtEmpty">
            今天两个 TOP 10 没有交集，不勉强制造共振。
          </div>
        )}
      </section>

      <section className="rtStrict">
        <div className="rtSectionTitle">
          <div>
            <p>02 / 严格组合</p>
            <h2>MACD传导 + RSI底背离</h2>
          </div>
          <span>比榜单交集更严格</span>
        </div>
        <div className="rtStrictGrid">
          {data.combined_top10.map((x) => (
            <article key={x.symbol}>
              <header>
                <mark>严格组合</mark>
                <b>{x.symbol}</b>
                <strong>{x.combined_score}分</strong>
              </header>
              <p>{x.chain_reason}</p>
              <footer>
                <span>RSI：{x.rsi_divergence_frames.join("、")}底背离</span>
                <span>量能：{x.volume.label}</span>
              </footer>
            </article>
          ))}
        </div>
      </section>

      <section className="rtSignals">
        <div className="rtSectionTitle">
          <div>
            <p>03 / MACD</p>
            <h2>零轴下优先 · 小周期带大周期</h2>
          </div>
          <span>日线 → 周线 → 月线</span>
        </div>
        <SignalBoard items={data.macd_top10} kind="macd" overlap={overlap} />
      </section>
      <section className="rtSignals">
        <div className="rtSectionTitle">
          <div>
            <p>04 / RSI</p>
            <h2>超卖修复与底背离</h2>
          </div>
          <span>价格新低，RSI低点抬高</span>
        </div>
        <SignalBoard items={data.rsi_top10} kind="rsi" overlap={overlap} />
      </section>

      <section className="rtVolume">
        <div className="rtSectionTitle">
          <div>
            <p>05 / VOLUME</p>
            <h2>成交量异动</h2>
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
        <b>如何理解：</b>
        双指标交集是优先复核名单，不等于立即买入。放量下跌只做风险提示；周线和月线在周期收盘前仍可能变化。
      </footer>
    </main>
  );
}
