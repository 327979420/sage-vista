"use client";
import { useEffect, useMemo, useState } from "react";
type Audit = {
  status: string;
  provider: string;
  universe: {
    primary_exchange_common_active: number;
    primary_exchange_common_delisted: number;
    symbol_collisions: number;
  };
  history_checks: {
    symbol: string;
    rows: number;
    first: string;
    last: string;
    missing_adjusted_close: number;
    duplicate_dates: number;
  }[];
  corporate_actions: Record<string, number>;
  limitations: string[];
};
type Metric = {
  factor: string;
  horizon: number;
  mean_ic: number | null;
  ic_positive_pct: number | null;
  observations: number;
  spread: number | null;
};
type Pilot = {
  status: string;
  sample: {
    requested_active: number;
    requested_delisted: number;
    loaded: number;
    eligible_active: number;
    eligible_delisted: number;
    stock_months: number;
    dates: number;
    start: string;
    end: string;
  };
  metrics: Metric[];
  decision: string;
  limitations: string[];
};
type Combo = {
  combination: string;
  horizon: number;
  dates: number;
  observations: number;
  mean_ic: number | null;
  ic_positive_pct: number | null;
  spread: number | null;
};
type Stats = {
  periods: number;
  mean_return: number;
  win_rate_pct: number;
  annualized_sharpe: number | null;
  compounded_return: number;
  max_drawdown: number;
};
type Portfolio = {
  combination: string;
  average_holdings: number;
  cost_scenarios_bps: Record<
    string,
    { absolute: Stats; excess_vs_eligible_universe: Stats }
  >;
};
type AtrRisk = {
  combination: string;
  atr_multiple: number;
  median_r: number;
  trade_win_rate_pct: number;
  average_holding_days: number;
  average_position_pct: number;
  portfolio: Stats;
};
type Validation = {
  status: string;
  sample: {
    loaded: number;
    eligible_active: number;
    eligible_delisted: number;
    stock_months: number;
    dates: number;
    start: string;
    end: string;
  };
  execution: { entry: string; time_stop: string };
  combinations: Record<string, Combo[]>;
  portfolios: Record<string, Portfolio[]>;
  atr_risk: Record<string, AtrRisk[]>;
  decision: string;
  limitations: string[];
};
const names: Record<string, string> = {
  volatility_contraction: "Volatility contraction",
  breakout_252: "52-week breakout",
  low_volatility: "Low volatility",
  liquidity: "Liquidity",
  rsi_14: "RSI (14)",
  momentum_12_1: "12–1 momentum",
  volume_expansion: "Volume expansion",
  trend_quality: "Trend quality",
  relative_strength_6m: "Relative strength",
};
export default function DataQuality() {
  const [audit, setAudit] = useState<Audit | null>(null),
    [pilot, setPilot] = useState<Pilot | null>(null),
    [validation, setValidation] = useState<Validation | null>(null);
  useEffect(() => {
    Promise.all([
      fetch("/data-audit.json").then((x) => x.json()),
      fetch("/eodhd-factor-pilot.json").then((x) => x.json()),
      fetch("/eodhd-factor-validation.json").then((x) => x.json()),
    ]).then(([a, p, v]) => {
      setAudit(a);
      setPilot(p);
      setValidation(v);
    });
  }, []);
  const top = useMemo(
    () =>
      pilot?.metrics
        .filter((x) => x.horizon === 60)
        .sort((a, b) => (b.mean_ic ?? -9) - (a.mean_ic ?? -9))
        .slice(0, 6) ?? [],
    [pilot],
  );
  if (!audit || !pilot || !validation)
    return <main className="datalab">Loading provider audit…</main>;
  const forward = validation.combinations.forward_test;
  const forwardPortfolio = validation.portfolios.forward_test;
  const forwardAtr = validation.atr_risk.forward_test.filter(
    (x) => x.atr_multiple === 2.5,
  );
  return (
    <main className="datalab">
      <header>
        <p className="label">NORTHSTAR / DATA QUALITY</p>
        <h1>Trust the history before the result.</h1>
        <span>
          EODHD is now the candidate source for survivorship-aware price
          research.
        </span>
      </header>
      <section className="datastats">
        <div>
          <small>HISTORIES LOADED</small>
          <b>{validation.sample.loaded.toLocaleString()}</b>
          <span>active and delisted sample</span>
        </div>
        <div>
          <small>EVER ELIGIBLE</small>
          <b>
            {validation.sample.eligible_active +
              validation.sample.eligible_delisted}
          </b>
          <span>
            {validation.sample.eligible_active} active +{" "}
            {validation.sample.eligible_delisted} delisted
          </span>
        </div>
        <div>
          <small>STOCK-MONTHS</small>
          <b>{validation.sample.stock_months.toLocaleString()}</b>
          <span>
            {validation.sample.start} → {validation.sample.end}
          </span>
        </div>
        <div>
          <small>TESTED FACTORS</small>
          <b>13 + 3</b>
          <span>individual factors + combinations</span>
        </div>
      </section>
      <section className="datagrid">
        <article>
          <p className="label">ATR RISK TEST · 2.5× STOP</p>
          <h2>2026 gap-aware monitor</h2>
          <div className="pilothead">
            <span>Combination</span>
            <span>Return</span>
            <span>Drawdown</span>
          </div>
          {forwardAtr.map((x) => (
            <div className="pilotrow" key={x.combination}>
              <b>{x.combination.replaceAll("_", " ")}</b>
              <span>{(x.portfolio.compounded_return * 100).toFixed(2)}%</span>
              <span>{(x.portfolio.max_drawdown * 100).toFixed(2)}%</span>
            </div>
          ))}
          <mark>
            0.5% intended risk per trade, 4% total-risk cap, 10% maximum
            position, 2R target, and forced exit after 10 candles.
          </mark>
        </article>
        <article>
          <p className="label">CURRENT FINDING</p>
          <h2>Wider stops survived better</h2>
          <p>
            The 2.5× ATR stop was more robust than 1.5× or 2× in the long
            development period. It reduced premature exits, but still has not
            earned live-trading status.
          </p>
        </article>
      </section>
      <section className="datagrid">
        <article>
          <p className="label">PORTFOLIO TEST · 0.20% COST</p>
          <h2>2026 excess return monitor</h2>
          <div className="pilothead">
            <span>Combination</span>
            <span>Mean</span>
            <span>Drawdown</span>
          </div>
          {forwardPortfolio.map((x) => {
            const stats =
              x.cost_scenarios_bps["20"].excess_vs_eligible_universe;
            return (
              <div className="pilotrow" key={x.combination}>
                <b>{x.combination.replaceAll("_", " ")}</b>
                <span>{(stats.mean_return * 100).toFixed(2)}%</span>
                <span>{(stats.max_drawdown * 100).toFixed(2)}%</span>
              </div>
            );
          })}
          <mark>
            Excess return is measured against the equally weighted eligible
            universe, after the cost haircut.
          </mark>
        </article>
        <article>
          <p className="label">WHY THIS MATTERS</p>
          <h2>Market return is not alpha</h2>
          <p>
            A candidate must outperform other eligible stocks after costs—not
            merely rise while the broad market is strong.
          </p>
        </article>
      </section>
      <section className="datagrid">
        <article>
          <p className="label">HISTORY AUDIT</p>
          <h2>{audit.status.replaceAll("_", " ")}</h2>
          {audit.history_checks.map((x) => (
            <div className="historycheck" key={x.symbol}>
              <b>{x.symbol}</b>
              <span>
                {x.first} → {x.last}
              </span>
              <small>
                {x.rows.toLocaleString()} bars · {x.duplicate_dates} duplicate
                dates
              </small>
            </div>
          ))}
        </article>
        <article>
          <p className="label">2026 FORWARD MONITOR · 10 DAYS</p>
          <h2>Combination behavior</h2>
          <div className="pilothead">
            <span>Combination</span>
            <span>IC</span>
            <span>Spread</span>
          </div>
          {forward.map((x) => (
            <div className="pilotrow" key={x.combination}>
              <b>{x.combination.replaceAll("_", " ")}</b>
              <span>{x.mean_ic?.toFixed(3)}</span>
              <span>
                {x.spread === null ? "—" : `${(x.spread * 100).toFixed(2)}%`}
              </span>
            </div>
          ))}
          <mark>
            Only {forward[0]?.dates ?? 0} monthly dates are available in 2026.
            This is monitoring evidence, not promotion evidence.
          </mark>
        </article>
      </section>
      <section className="datagrid">
        <article>
          <p className="label">EXECUTION REALISM</p>
          <h2>Signal close → next open</h2>
          <p>
            {validation.execution.entry}. {validation.execution.time_stop}.
          </p>
        </article>
        <article>
          <p className="label">DECISION</p>
          <h2>Research only</h2>
          <p>{validation.decision}</p>
        </article>
      </section>
      <section className="datalimits">
        <p className="label">WHAT STILL BLOCKS PROMOTION</p>
        {validation.limitations.map((x) => (
          <span key={x}>{x}</span>
        ))}
      </section>
    </main>
  );
}
