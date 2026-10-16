# Task 007: how optimistic is the full-history bad-data filter? (diagnostic)

Read `tasks/README.md` first. Pre-registered in ledger section 17 ("坏数据筛选·偷看未来"). Workbench ticket SV-17.

## Why
`research/lab/selection.py::impossible_jumps` drops a stock entirely if its close EVER moves > 4x up or > 90% down in one session,
over the whole file (before 2005 and after 2025 included). A real one-day collapse in 2020 therefore removes that stock from
2005-2019 as well: the backtest "knows" which stocks will later blow up. Every 3W result so far used this filter.

## Do (no change to the filter itself or to any rule)
1. List the flagged symbols in the datasets the 3W builder uses (`work/v3w/components.py` / `fair19` path) and, for each, the
   date(s) of the impossible jump(s).
2. Build 3W candidates for the flagged symbols only, with the same frozen builder and the same data boundary as tasks 002/003
   (warm-up allowed; no signal/trade/statistic before 2005-01-01 or after 2025-06-30). Use the same eligible-pool rules.
3. Three variants of the candidate list:
   - BASE: today's (flagged symbols excluded) - must reproduce 6.9132% / 0.6724 / 24.8143%;
   - PIT: a flagged symbol's signal is excluded only if one of its impossible jumps happened on or before the signal date;
   - NONE: no exclusion at all.
   For PIT and NONE report: number of extra candidates, their standalone R (count, mean, worst 10 with dates, symbols hidden),
   and the account (baseline engine and rules) under the same 200 random orderings as task 002 (P10/P50/P90 of CAGR, Sharpe,
   max drawdown).
4. Pre-registered reading: if PIT's median Sharpe is lower than BASE's median (0.654) by more than 0.05, say "earlier results were
   materially optimistic" and give the PIT numbers as the new honest reference; otherwise "the filter's look-ahead is small".
   NONE is descriptive only (it includes true provider errors).

## Deliverables
`work/v3w/pit_filter.py` + `.log`, `work/reports/pit-filter-v1.{json,html}` (simple Chinese, inline SVG), codex report with Concerns.
No tests in `tests/` that import `work/`. No changes to `selection.py`, frozen code or production. No network, no commits.
