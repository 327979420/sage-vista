# Task 016: Signal funnel - where do 3W signals drop out? (description only)

Read `tasks/README.md` first. Owner request (2026-10-17: "做"): why does the frozen 3W find so few signals (HK group A: 124 signals,
14 trades in 20 years)? This is a DESCRIPTION. No rule changes, no new variants, no verdict, nothing tuned. HK group A is already used
(task 010), so counting on it spends no locked data. HK group B, HK before 2005 and US 1985-2004 must not be loaded for this.

## What to count (same order as the code applies the gates)
For each market, count how many stock-weeks / candidates survive each gate of `research/lab/triangle15.py` `signals()` and `_shape()`,
then of the trade path used by the exams (`work/v3w/fair19.py` `one()` / `hk_exam.py`):
1. stock-weeks with enough history (n >= 80 weeks) in the window, and stock-weeks where the stock is in the tradable pool;
2. bullish weeks (close > open);
3. + weekly MACD golden cross this week after >= 4 weeks under (and >= 13 weeks since the last signal);
4. + a converging triangle push line with a last bottom before this week and the week's low within 1.5 weekly ATR of it;
5. `_shape` gates, each separately in code order: pullback 10%..60%; flat bottoms (last <= lowest x 1.10, >= 2 bottoms); not a new
   3-year low; stop distance >= minimum ATR; a target >= 7% over the close exists above the stop; reward-to-risk fallback check;
6. + DIF under zero; + inside the signal window and tradable that day  -> must equal the known signal count;
7. trade path: plan "go" (split by reason: reward-to-risk < 1.5, monthly MACD veto, other), market filter (index over its 200-day
   line, breadth over half - split by which one failed), limit order not filled within 8 weeks / cancelled, trade not finished
   -> must equal the known trade count.

Do NOT edit frozen code. Re-implement the counting in `work/v3w/funnel.py` by calling the frozen helpers and mirroring the gate order;
the final counts MUST reconcile exactly with the frozen code: HK A (hk-a-1995-v1, exam settings of task 010) 124 signals / 14 trades;
US development data (the five datasets, 2005-01..2024-06 signals as fair19) 2,716 signals / 571 trades. If they do not reconcile,
stop and ask - do not adjust the mirror until it "fits" without explaining why.

## Report (`work/reports/signal-funnel-v1.{json,html}`, simple Chinese, inline SVG bar funnel)
Both markets side by side: count after each gate, share kept at each gate, and "signals per 100 stock-years". Name the single biggest
drop for each market. Note that the US numbers are development data. No recommendations to loosen rules - if a gate looks
decisive, say so as a fact only; any rule change would be a new version with its own registration.

## Deliverables
`work/v3w/funnel.py` + log, the report, codex report with Concerns. No network, no commits, no tests importing `work/`.

## Decision (2026-10-17, Claude, answering Codex before any work)
`signals()` scans shapes from week 60 and filters by date afterwards, so pre-2005 shapes set the 13-week cooldown. Reuse that exactly
(it is how 2,716 / 124 were produced, not a new use of locked data). Count and report only signal weeks inside the window; gates 1-5
count only in-window stock-weeks; a cooldown started before the window is one number ("weeks blocked by a cooldown that started before
the window"), with no pre-2005 detail. State this in the report's 口径 section and the script docstring.
