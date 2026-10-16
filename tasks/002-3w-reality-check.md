# Task 002: 3W reality check (diagnostic only; no rule changes)

Read `tasks/README.md` first. Pre-registered in `docs/CASE_REVIEW_LEDGER_ZH.md` section 17 ("3W 现实检验") before any run.

## Why
The frozen 3W 1.9 account (2005-01-03 to 2025-06-30) shows CAGR 6.9%, Sharpe 0.67, max drawdown 24.8%. Before we optimise 3W any
further, the owner needs to know whether that number is robust to things a real trader cannot control. Nothing here changes the rule.

## Data boundary (clarified 2026-10-16 after Codex's stop)
- Allowed: the baseline builder loads full price files and computes indicators/shapes with history before 2005 as warm-up. That is
  not "using locked data" here: no signal dated before 2005-01-01 and no trade result before 2005 is produced, read or reported.
- Allowed, but a documented limitation: `selection.impossible_jumps` screens bad-data stocks over each file's full history (it can
  see later prices). Keep it exactly as the baseline does, and list it under limits in the report. Do not change it.
- Still forbidden: any signal, trade, or statistic dated before 2005-01-01 or after 2025-06-30; any HK data.
- Step C's ADV uses only the 20 sessions before entry (unchanged).

## Baseline (reproduce first, stop if it does not match)
Build the 3W candidate list exactly as `work/v3w/components.py` does (it reuses `fair19`'s builder and the frozen code), run
`research.lab.account.run_account` with `approved_scenario()` and rules `{"risk_per_trade": 0.02, "position_cap": 0.20,
"max_positions": 10, "heat_cap": 0.10}`. Target: CAGR 6.91%, Sharpe 0.672, max drawdown 24.81% (tolerance 0.05 pp / 0.005).
Save the candidates once to `work/v3w/w3_cands.json` so later steps do not rebuild them.

## Step A: slot luck
All 3W candidates have priority 0, so when more than 10 signals compete, list order decides who gets a slot. Run the account 200
times, each with candidate priorities set to a random permutation (numpy-free `random.Random(seed)` with seeds 1..200). Report the
distribution (5th, 10th, 50th, 90th, 95th percentiles) of CAGR, Sharpe and max drawdown, and the baseline's percentile in it.

## Step B: costs
Baseline account with `cost_rate` 0.001 (baseline), 0.0025 and 0.005 per side. Nothing else changes.

## Step C: capacity
For each trade the baseline account actually took: position dollars / average daily dollar volume of the 20 sessions before entry
(use the dataset's volume and close; only data up to the day before entry). Scale the account to $1M and $10M by multiplying position
dollars by 10 and 100 (no re-simulation). Report, for $100k / $1M / $10M, the share of trades above 1% and above 5% of that ADV and
the median ratio.

## Step D: stop gaps
From the baseline account's trades: the distribution of realised R (per-trade return / initial risk); count and total R of trades
worse than -1.2R (stop jumped by a gap); the worst 10 trades (symbol hidden: use an index) with entry date and R.

## Pre-registered reading (write the verdict for each, no changes afterwards)
- A passes if the 10th percentile Sharpe is >= 0.55 and the baseline sits between the 10th and 90th percentiles.
- B passes if Sharpe at 0.25% per side is >= 0.55.
- C passes if at $1M no more than 10% of trades exceed 5% of ADV.
- D is descriptive: report how much total R the gap trades cost versus the rule's -1R assumption.

## Deliverables
1. `work/v3w/reality3w.py` (all steps, reproducible from the cached candidates) and `work/v3w/reality3w.log`.
2. `work/reports/3w-reality-v1.json` (all numbers) and `work/reports/3w-reality-v1.html`: simple Chinese for a non-programmer,
   self-contained, inline SVG (histogram of the 200 Sharpe values with the baseline marked; bar chart of costs), one-sentence
   conclusion per step, and limits.
3. `work/reports/3w-reality-v1-codex-report.md`: what you did, baseline match, results, deviations, commands.

## Forbidden
Locked data (US before 2005, any HK, after 2025-06-30), frozen code (`triangle15.py`, `triangle_forward.py`, `research/lab/forward/`),
production paths. No new rule variants, no tuning, no commits. If the baseline does not match, stop and report.
