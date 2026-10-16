# Task 005: decision-layer test (sector cap, gaps first, swaps) on the 3W account

Read `tasks/README.md` first. Owner decision ADR-8 (accepted 2026-10-17). Pre-registered in ledger section 17 ("组合决策层·测试").
Starts only after task 004 phase B is accepted (needs `data/industry/ff12-sic-v1.json`).

## Do not touch the existing engine
`research/lab/account.py::run_account` is used elsewhere. Write a new module `research/lab/decision.py` with
`run_account_decision(trades, n_days, scenario, rules, industry, decision)` that copies `run_account`'s logic and adds the rules
below. Unit tests in `tests/test_decision.py` (repo code, so tests belong in tests/, using synthetic trades only):
- with every decision rule off it returns exactly what `run_account` returns (equity, exposure, trades, skipped) on synthetic data;
- sector cap blocks the 4th position of one industry; unknown industry is never capped;
- gap-first ordering only reorders same-day entries; swap sells exactly one holding, at the stated price, with fees, and the sold
  trade's later exits are ignored; no decision uses a price later than the previous close.
Also check on the real cache: all rules off reproduces task 002's baseline (6.9132% / 0.6724 / 24.8143%).

## The rules (fixed; do not tune)
- `industry`: symbol -> FF12 code from `data/industry/ff12-sic-v1.json`; missing -> "UNKNOWN".
- A. **Sector cap**: at most 3 open positions per FF12 industry (UNKNOWN not capped). A blocked signal is skipped ("sector_cap").
- B. **A + gaps first**: same-day entries are taken in order of how many positions their industry holds at the start of that day
  (fewest first); ties keep the run's random order.
- C. **Swap when full** (no cap, no reordering): if a signal is skipped for cash/whole shares or the position limit, look at holdings
  held >= 40 sessions; compute each one's unrealised R with the PREVIOUS close ((close - entry) / (entry - stop)). If the lowest is
  < +0.5R, sell that one at TODAY's close (fee 0.1%), then try the new entry once more with the proceeds. At most one swap per day.
  Approximation to state in the report: the sale is at today's close but its cash is used for an entry filled earlier that day.

## Evaluation (pre-registered)
For each of A, B, C run the same 200 random orderings as task 002 (`permuted(..., seed)` seeds 1..200) and report the distribution
(P10/P50/P90) of CAGR, Sharpe, max drawdown, and median CAGR per decade (2005-2014, 2015-2025), next to the baseline distribution
from task 002 (Sharpe median 0.654, max drawdown median 26.3%). A rule is "useful" if EITHER
 (1) median Sharpe >= 0.654 + 0.03 and median max drawdown <= 26.3% + 1 pp, OR
 (2) median max drawdown <= 26.3% - 2 pp and median Sharpe >= 0.654 - 0.02,
AND in both decades the median CAGR is not more than 1 pp below the baseline's decade median. Also report: positions per industry,
number of sector-cap skips, swaps, and the R of swapped-out trades had they been held (hindsight, descriptive only).

## Deliverables
`research/lab/decision.py`, `tests/test_decision.py`, `work/v3w/decision_test.py` + `.log`,
`work/reports/decision-test-v1.{json,html}` (simple Chinese, inline SVG: Sharpe and drawdown distributions per rule vs baseline),
`work/reports/decision-test-v1-codex-report.md` with Concerns.

## Forbidden
Same data boundary as tasks 002/003. Do not modify `account.py`, frozen code or production. No tuning, no extra variants, no commits.
