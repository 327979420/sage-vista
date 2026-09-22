# Sage Vista

### From market noise to a short list of explainable trade setups.

Sage Vista is a quantitative trading research platform that scans U.S. equities, surfaces setups worth investigating, explains the evidence behind them, and tracks what happens next.

**[Live Demo](https://sage-vista-parallel.gizmo-allied-0s.workers.dev/zh/watch/resonance/rare-opportunities) · [中文](./README.zh-CN.md) · [Documentation](./docs/SAGE_VISTA_RULEBOOK_ZH.md)**

Choose **English** in the top-right language switch.

<!-- Screenshot 1: English multi-factor opportunity / ranking page (hero).
     Reserved path: docs/assets/product/opportunity-ranking.en.png
     Pending a verified capture of the production English interface. -->

> **Scan → Rank → Explain → Test → Improve**

## What Sage Vista Does

- **Discover** — Turn a broad stock universe into a focused research list.
- **Explain** — See chart structure, signals across timeframes and supporting factors.
- **Add context** — Evaluate market, sector and risk conditions alongside each setup.
- **Validate** — Backtest ideas and track signals, preserving successes and failures.

## How It Works

**Market Data → Screening → Pattern & Factor Analysis → Market / Sector Context → Ranking → Tracking → Validation**

Scores summarize evidence within the model. They are not probabilities of profit or guarantees of returns.

## Product

### Pattern & Evidence

<!-- Screenshot 2: English pattern / evidence detail.
     Reserved path: docs/assets/product/pattern-evidence.en.png -->

Understand why a setup was selected through price structure and signals across monthly, weekly and daily timeframes.

### Market & Sector Context

<!-- Screenshot 3: English market / sector context.
     Reserved path: docs/assets/product/market-sector-context.en.png -->

See whether the broader environment supports or challenges the setup, with stock-level evidence kept distinct.

### Research & Validation

<!-- Screenshot 4: English research / backtesting view.
     Reserved path: docs/assets/product/research-validation.en.png -->

Explore historical tests and signal tracking, including failed ideas and results that need more evidence.

<details>
<summary>Research snapshot: archived results, methodology & limitations</summary>

| Historical Events Audited | Registered Factors | Registered Experiments | 2026 20-Day Samples |
|---:|---:|---:|---:|
| **62,000+** | **39** | **41** | **1,166** |

**Archived 2026 baseline · 20-trading-day holding window**

**54.3% win rate · 1.51 profit factor · +2.10% average event return before costs**

Daily MACD cross events, entered at the next session's adjusted open; repeat events per stock are excluded within 120 trading days. The study ends on **28 August 2026**. Average event return falls to **+1.60%** with a 0.50% cost assumption.

These are historical event-study results, not live or paper portfolio returns or evidence that today's ranking predicts returns. Higher scores did not consistently produce better outcomes in this study; historical delisted-stock coverage is partial.

[Study & limitations](./research/preregistrations/score-timeframe-attribution-v2.md) · [Result data](./research/backtest/output/score-timeframe-attribution-v2.json). Factor count: [registry v0.10.0](./public/factor-registry.json); experiments: [13 September 2026 catalogue](./research/generated/experiment-catalog.json), including unfinished work.

</details>

## Where It's Going

Sage Vista started as a stock picker and is evolving toward a fuller trading system:

**Research → Decision → Trade Plan → Paper Execution → Risk Management → Performance Analysis**

Today's focus is research, testing and human decision support. Live automated order execution is not part of the system.

## Tech & Development

`Python` · `TypeScript` · `React` · `Cloudflare`

Run the web app locally with **Node.js 22.13.0 or newer**:

```bash
npm install
npm run dev
```

Explore the [product & methodology](./docs/SAGE_VISTA_RULEBOOK_ZH.md), [architecture](./docs/SYSTEM_ARCHITECTURE_ZH.md), [research](./research/README.md) and [recorded project status](./docs/CURRENT_STATUS_ZH.md). The demo supports English and Chinese. Most detailed documentation and archived reports are in Chinese.

Contributor and agent workflow: [AGENTS.md](./AGENTS.md) · [governance](./docs/rules/01_GOVERNANCE.md).
