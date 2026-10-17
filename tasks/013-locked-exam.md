# Task 013: the final exam on locked US data (1985-2004) - frozen 3W and the candidate portfolio

Read `tasks/README.md` first. Owner decision (2026-10-17: "考"). Pre-registered in ledger section 17 ("锁定数据大考") before running.
This is a ONE-TIME exam on data never used for 3W research. If anything is unclear or you find a bug, STOP and ask before producing
final numbers. Nothing may be tuned after seeing results.

## Data
- Stocks: the same datasets and builder path the US validation used (`work/v3w/fair19.py` / `components.py`, `B11.DATASETS`), but
  only dates before 2005-01-01 for signals and results (this is the locked part). SPY from the same data (starts 1993-01-29).
- Sector ETFs: `sector-etf-1998-to-2026-10-v1` (start 1998-12-22).
- Known, stated limitation: the stock lists were built from stocks alive in 2005-2025, so stocks that died before 2005 are missing
  (survivorship bias). Absolute returns are inflated; comparisons against random picks from the SAME pool are the meaningful part.

## Part A - frozen 3W (3w-1.9), unchanged rules and account
Signals 1994-01-01 .. 2003-12-31 (SPY's 200-day filter is available from late 1993; leaves a year for trades to finish); account and
random accounts marked to 2004-12-31; cost 0.1% per side; same account rules as task 002. 1,000 random accounts as fair19 step 3.
Verdict A: PASS if the full-period Sharpe p-value <= 0.05. Report CAGR, Sharpe, max DD, trades, exposure, p for CAGR, by
1994-1999 / 2000-2004, and SPY buy-and-hold for the same window.

## Part B - sector trend basket (core), same rules as `work/v3w/sector_trend.py` v2
Window 1999-11-01 .. 2004-12-31 (200-day SMA ready). Compare SECT-TREND vs EQ-SECT vs SPY (and TREND).
Verdict B: useful if Sharpe >= EQ-SECT + 0.10 and max DD <= EQ-SECT - 15 pp (same rule as registered for 2005-2025).

## Part C - core + satellite 50/50 (as `work/v3w/core_satellite.py` v2: first-day cost kept, exact Sharpe)
Same window as B, using Part A's 3W account curve over that window (rescaled to start 100,000) and Part B's SECT-TREND.
Verdict C: Sharpe >= max(core, 3W) + 0.05 and max DD <= min(core, 3W) + 5 pp.

## Deliverables
`work/v3w/locked_exam.py` + `.log`, `work/reports/locked-exam-v1.{json,html}` (simple Chinese, inline SVG), codex report with
Concerns. Reuse existing code; do not edit frozen code, research/lab/account.py, services/ or production. No tests in `tests/`
importing `work/`. No network, no commits. After this exam the 1985-2004 data is no longer "unseen" - say so in the report.
