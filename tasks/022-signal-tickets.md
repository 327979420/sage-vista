# Task 022: signal evidence tickets (data only)

Read `tasks/README.md` first. Owner (2026-10-18): every 3W signal needs a "凭证" (ticket) showing the evidence for the buy - which
conditions triggered, the three pushes, the bottoms, the golden cross - not real-time, just provable. Design reference: the
"信号凭证" page of Claude's prototype `work/site-v2/sv-dashboard-prototype.html` (open it in a browser). Pages come later; this card is
the data.

## Output
`public/app/tickets/<signal_id>.json`, one per 3w-1.9 signal record (append-only like signals.jsonl; never rewritten after creation
except the `outcome` block), plus `public/app/tickets/index.json` (id, symbol, signal_week, status, outcome R). Each ticket:
- `checks`: every gate of triangle15 `signals()`/`_shape()` and the trade plan, in code order, each with its measured value and pass
  (pullback %, flat-bottom %, not-a-3-year-low, stop distance vs ATR, target >= 7%, reward-to-risk, DIF under zero, golden cross after
  >= 4 weeks under, tradable-pool facts, monthly MACD veto, SPY vs 200-day, breadth with sample size). Values must come from the frozen
  code's own computations (call its helpers; do not re-derive rules). If a value is not exposed by the frozen code, compute it in the
  new module with a test proving it reproduces the frozen decision on fixtures - and say so in `checks[i].derived: true`.
- `pushes`, `bottoms` (dates + prices), `trend_line` (two anchor points), `order` (limit, stop, target, R, valid until, max hold),
  `weekly`: OHLC + DIF/DEA for ~60 weeks around the signal, `outcome` (waiting/filled/closed, dates, exit, R) from outcomes.json.
- Size: each ticket < 60 KB.

## Wiring and tests
Build inside `research/lab/app_data.py` (same publish step; same window guard). Tests with fixtures: one passing ticket, one blocked by
the market filter (checks show which one failed), reproducible bytes, size guard, tickets never rewritten except `outcome`.
Also produce a sample from history (2-3 signals from the development data, marked `"example": true`) into `work/app-data/tickets/`
for the page work - not published.

Stop and ask if a gate value cannot be obtained without changing frozen code. No network, no commits.

## Decision (2026-10-18, Claude)
outcomes.json keeps only status and R for 3w-1.9. Fill outcome dates/exit by calling the frozen trade(..., hold=130, target=3R) as the
forward record does; cross-check R against r19 in outcomes.json; on mismatch -> dates/exit null, status "unverified", reported.
