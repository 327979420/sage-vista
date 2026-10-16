# Task 010: the frozen 3W (3w-1.9) sits the Hong Kong exam once (group A)

Read `tasks/README.md` first. Pre-registered in ledger section 17 ("3W 港股考试") and docs/rules/08 #hk-exam before running.
This is an EXAM: run it once. If you find a bug or anything unclear, STOP and report before running the final numbers.

## Fixed (do not change)
- Rules: the frozen 3W exactly as in the US validation (`work/v3w/fair19.py` path: `research/lab/triangle15.py` signals, plan and trade;
  monthly veto; pullback limit; stop; 3R target; 26 weeks; same account rules: 100,000 start, 2% risk, 20% cap, 10 positions,
  10% heat cap). Do not edit the frozen code.
- Data: `hk-a-1995-v1` (442 symbols: group A + Tracker Fund 2800), already in `work/lab/`. Group B
  (`research/lab/universes/hk-exam-b-v1.txt`) is LOCKED: never load or mention its symbols.
- Period: signals and results 2005-01-01 .. 2025-06-30 only; earlier HK prices are indicator warm-up only.
- Local conditions (the only changes, fixed in docs/rules/08 #hk-exam): HK pool = `{"min_history": 420, "min_close": 1.0,
  "min_dollar_volume": 7.8e7, "raw_close": True}` (HK$1 unadjusted close, HK$78M traded); 2800 replaces SPY in the market filter
  (2800 close above its 200-day mean AND more than half of a 300-stock sample of the HK data above their own 200-day mean, same
  code as `fair19.market_ok`); 2800 is a fund and is never a candidate; cost 0.2% per side; the same full-history bad-data filter
  as the US baseline (`selection.impossible_jumps`), listed as a limitation.

## Measure
1. The 3W account on group A: CAGR, Sharpe, max drawdown, trades, exposure; decades 2005-2014 / 2015-2025.
2. Luck: 1,000 random accounts (each taken signal replaced by a random same-day HK pool stock, same mechanics, as fair19 step 3),
   p = (1 + random accounts at or above 3W) / (1 + 1000) for Sharpe and CAGR, full period and decades. No matched-random step
   (no HK sectors).
3. Benchmarks: 2800 buy and hold; 2800 held at 3W's own daily invested share (rest cash).

## Pre-registered verdict
PASS if the full-period Sharpe p-value <= 0.05 ("3W beats random HK stock picks"). Everything else is descriptive.

## Deliverables
`work/v3w/hk_exam.py` + `.log`, `work/reports/hk-exam-v1.{json,html}` (simple Chinese, inline SVG, no pre-2005 results, no
group-B symbols), codex report with Concerns. No tests in `tests/` importing `work/`. No network, no commits.
