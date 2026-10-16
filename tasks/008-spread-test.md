# Task 008: "pick less, hold more" - more, smaller 3W positions at the same total risk

Read `tasks/README.md` first. Owner approved 2026-10-17. Pre-registered in ledger section 17 ("少挑多拿").

## Why
Task 002/003: 47% of 3W signals never get a slot, and which ones do is luck (Sharpe P10-P90 0.622-0.691 across 200 orderings).
Holding more, smaller positions should take more signals and reduce that luck. Total risk is kept equal so any change comes from
spreading, not from taking more risk.

## The one variant (fixed; do not tune)
Same engine (`research.lab.account.run_account`, `approved_scenario()`, cost 0.1%), same candidates (`work/v3w/w3_cands.json`):
- BASE: max_positions 10, risk_per_trade 0.02, position_cap 0.20, heat_cap 0.10 (task 002 baseline)
- SPREAD: max_positions 20, risk_per_trade 0.005, position_cap 0.10, heat_cap 0.10
Run both under the same 200 random orderings as task 002 (`permuted(..., seed)` seeds 1..200).

## Report
P10/P50/P90 of CAGR, Sharpe, max drawdown; median CAGR per decade (2005-2014, 2015-2025); width P90-P10 of Sharpe; signals taken
and skipped by reason; average number of open positions and average exposure.

## Pre-registered verdict
SPREAD is "useful" if (1) median Sharpe >= 0.654 + 0.03, or (2) median max drawdown <= 26.3% - 2 pp with median Sharpe >= 0.634;
AND both decade median CAGRs are not more than 1 pp below BASE's. Separately report whether the Sharpe P90-P10 width is at least
30% narrower than BASE's 0.069 ("less luck"), descriptive.

## Deliverables / forbidden
`work/v3w/spread_test.py` + `.log`, `work/reports/spread-test-v1.{json,html}` (simple Chinese, inline SVG, no pre-2005 data shown),
codex report with Concerns. No tests in `tests/` importing `work/`. Same data boundary as task 002. No tuning, no extra variants,
no commits, no network.
