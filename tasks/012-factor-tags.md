# Task 012: factor tags for 3W candidates and holdings (context only, never a buy/sell rule)

Read `tasks/README.md` first. Owner request (2026-10-17): keep using the multi-factor work as CONTEXT - for every 3W candidate and
every open 3W position, show which factors are triggered. Tags never change what 3W buys or sells (the frozen 3w-1.9 is untouched).
Pre-registered in ledger section 17 ("因子标签").

## Part 1 - a small, reusable tagger (repo code)
New module `research/lab/factor_tags.py` (do NOT edit `services/`; import from it read-only):
- `entry_tags(rows, end)` -> list of triggered factor ids from the existing registry (`public/factor-registry.json`, 39 factors,
  version 0.10.0) evaluated point-in-time at bar `end`, using the existing detector/snapshot code in `services/scanner/`
  (`factor_detectors.py`, `factor_snapshot.py`, `detectors.py`). Reuse, do not re-implement, any factor that already has code. If a
  registry factor has no point-in-time code path, list it as "not available" instead of inventing it.
- `risk_tags(rows, end)` -> warnings for a held position, a short fixed list defined here (descriptive, not tuned):
  `macd.weekly_bear_cross` (complete weekly MACD line crosses below signal), `macd.monthly_high_bear_setup` (monthly MACD above zero and
  histogram falling 2 bars), `rsi.overbought` (daily RSI14 > 70), `rsi.bearish_divergence` (mirror of the existing bullish one if its
  code allows mirroring; otherwise "not available"), `structure.weekly_bearish_engulfing` (mirror of the bullish rule),
  `trend.below_ema200` (daily close < EMA200), `risk.overhead_unfilled_gap` (existing).
- Each tag returns id, Chinese label, direction (利好 / 利空), and the date it became true. Only data up to `end`.
- `tests/test_factor_tags.py`: synthetic data only (no work/ imports): no look-ahead (adding future bars never changes tags at `end`),
  mirrored rules are symmetric on mirrored data, unknown/not-available factors are reported, not guessed.

## Part 2 - history as clues, not evidence (descriptive)
On the 571 cached 3W signals (`work/v3w/w3_cands.json`, prices loaded as `work/v3w/components.py` does; same data boundary as task 002):
1. Entry tags at the entry date (use the previous session as `end`): for each tag with at least 20 signals, count, mean standalone R
   (task 003 definition), win rate, and the same for signals without the tag; split by decade.
2. Risk tags during holding: for each trade, the first week each risk tag appears after entry (only states that become true AFTER
   entry count - the task 011 lesson); mean R of trades with vs without each warning; how often a warning came before a stop vs
   before a 3R target.
Write clearly in the report: this data has been used ~785 times; these are clues for the forward record, not rules.

## Deliverables
`research/lab/factor_tags.py`, `tests/test_factor_tags.py`, `work/v3w/factor_tags_history.py` + `.log`,
`work/reports/factor-tags-v1.{json,html}` (simple Chinese, inline SVG, no pre-2005 data), codex report with Concerns. No changes to
services/, frozen code, production, or the forward record. No network, no commits.
