# Task 001 — Portfolio layer (TREND + MOMLV + 3W)

Owner: Codex (implementer). Reviewer and acceptance: Claude. Registered in docs/CASE_REVIEW_LEDGER_ZH.md section 17 ("组合层") BEFORE any run.
Read first: docs/START_HERE_ZH.md (working rules), docs/TRIANGLE_HANDOVER_ZH.md, work/v3w/tourney.py (the tournament this builds on), research/lab/account.py.

## Goal
Combine three low-correlated strategies from the tournament into portfolios and report, honestly, whether the combination beats the best single strategy on risk-adjusted terms.

## Inputs (all local; there is no network)
- Datasets already downloaded in work/lab/: universe-1985-v1, fresh-a..d-1995-v1, etf-core-2002-to-2026-10-v1 (load with research.lab.datasets.manifest/download/load exactly as tourney.py does).
- Component strategies exactly as implemented in work/v3w/tourney.py (corrected version: trades only the changes): TREND, MOMLV, 3W. Period 2005-01-03 .. 2025-06-30, cost 0.1% per side.

## Step 1 — component series (reproduce first)
1. Make tourney.py (or a new work/v3w/components.py that imports it) save each component's DAILY equity curve and invested share to work/v3w/components.json ({name: {dates, equity, exposure}}), plus SPY.
2. CHECK: recompute CAGR / Sharpe / max drawdown from the saved curves with research.lab.account.curve_stats. They must match the tournament table (work/v3w/tourney.log, corrected run) within 0.1 percentage point CAGR, 0.01 Sharpe, 0.2 pp drawdown: TREND 9.0% / 0.75 / 28.1%; MOMLV 9.1% / 0.72 / 38.7%; 3W 6.9% / 0.67 / 24.8%; SPY 10.4% / 0.61 / 55.2%. If they do not match, STOP and report why. Do not "fix" numbers.

## Step 2 — the combiner (repo code + tests)
Create research/lab/combine.py (pure functions, no I/O besides what the caller passes) and tests/test_combine.py.
- Input: daily return series of the sleeves on one calendar, target-weight rule, cost per side.
- Month-end rebalance: weights decided with data up to and including a month's last session; the sleeves are reset to target weights at the NEXT session (close-to-close returns from then on); between rebalances the sleeve weights drift with their returns.
- Cost: cost_per_side * (sum of |weight change| at the rebalance) taken from the portfolio that day.
- Portfolios (only these three; no other variants):
  - P1: 1/3 each.
  - P2: inverse volatility — weight_i ∝ 1 / stdev(last 252 daily returns of sleeve i) at the decision day; before 252 days exist, equal weights.
  - P3: P2 scaled by min(1, 0.10 / (stdev(last 63 daily returns of the P2 portfolio) * sqrt(252))) decided at the same month end; the rest earns 0 (cash). Never above 1 (no leverage).
- Tests must cover at least: no look-ahead (a return on the decision day's next session cannot change that month's weights), drift between rebalances, cost charged once per rebalance, P3 never above 100% invested, equal weights before 252 days.

## Step 3 — report
- Metrics per portfolio and per sleeve, using the tournament's report() definitions (CAGR, vol, Sharpe, Sortino, max DD, Calmar, average invested, beta/alpha vs SPY, CAGR 2005-2014 and 2015-2025, share of positive months) + correlation matrix of the sleeves' daily returns + rolling 36-month Sharpe + deflated Sharpe with n_trials = 777 and the trial variance from work/v3w/pf19.json as tourney.py computes it.
- Verdict per portfolio, exactly as registered: "useful" only if its Sharpe beats the best single sleeve's Sharpe in BOTH decades AND its max drawdown is at most the best single sleeve's max drawdown + 5 percentage points. Best single sleeve = the sleeve with the highest full-period Sharpe.
- Write work/reports/portfolio-v1.json (all numbers) and work/reports/portfolio-v1.html: a self-contained readable page IN SIMPLE CHINESE for a non-expert (the owner): what was tested in two sentences, a results table, an equity chart (log scale) and a drawdown chart drawn with inline SVG (no external libraries, no network), the verdict in one plain sentence, and a short "注意" list of limits (same 2005-2025 data used before; survivorship bias in universe-1985-v1; no deflated Sharpe reaches 0.95 → not proven).
- Write work/reports/portfolio-v1-codex-report.md for Claude: what you did, the Step-1 check numbers, the final table, anything that differed from this card and why, commands to reproduce.

## Do not
- Do not touch: research/lab/triangle15.py, research/lab/triangle_forward.py, research/lab/forward/, research/lab/datasets/ manifests, anything under docs/ except nothing (Claude edits docs), public/, app/, services/ (production), .github/.
- Do not use data before 2005-01-03 for results, any Hong Kong data, or any data after 2025-06-30.
- Do not add portfolios, change windows, weights, costs or the verdict rule. Do not tune anything.
- Do not commit or push (Claude reviews and commits).

## Acceptance (Claude will check)
1. Step-1 numbers match the tournament within the tolerances.
2. python3 -m unittest tests.test_combine passes and the tests really test the listed properties.
3. Spot check: Claude recomputes P1 from components.json with an independent few lines and compares CAGR/Sharpe.
4. No look-ahead in the weight code (read).
5. The HTML opens offline and says the verdict in plain Chinese; the numbers in it equal portfolio-v1.json.
6. git diff touches only: work/ (ignored), research/lab/combine.py, tests/test_combine.py, and optionally work/v3w/*.py.
