# Task 047 — Weekly report script: fresh prices and a one-day grace for the forward record (SV-64)

Read `tasks/README.md`, `research/lab/weekly_report.py`, its tests, `research/lab/app_data.py` (`portfolio`, `frozen_prices`),
`research/lab/paper.py` and `public/app/portfolio.json`. Owner decided 2026-10-26. The Saturday routine had to hand-write the
report because of two defects:

1. **Stale prices.** `main()` passes `app_data.frozen_prices(app_data.SECTOR)` — the offline dataset that ends early October —
   so every sector sleeve is marked stale and the SPY benchmark stops there.
2. **Forward record rejected.** `render()` refuses the forward record when `outcomes.computed_at[:10] > report_date`. The daily
   job computes it in UTC, often a day after the Melbourne report date, so a valid record is thrown away.

## Fix (no rule, number or threshold changes anywhere else)
- **Prices = the freshest outputs the daily Actions job already publishes, no new network calls in the script.**
  The rebalance card reads `public/app/portfolio.json` (same month-end signal, would-switch and stale flags the site shows).
  The SPY benchmark for the history metrics comes from the daily series of `research/lab/paper` (spy column) when present,
  else from `public/app/today.json`/portfolio data if they carry SPY closes; if neither covers the window → "不可用", never a
  guess. Keep `--sectors-frozen` as an explicit fallback flag for offline tests only.
- Each input's own date is shown in the report; an input dated after the report's valuation session is refused (no future data).
- **Forward record grace:** accept `outcomes.computed_at` up to 1 calendar day after the report date (UTC vs Melbourne), but
  refuse it if it is later than that; show `computed_at` in the card. Refusal text unchanged otherwise.

## Tests
Existing weekly-report tests stay green. Add: fresh portfolio.json → no stale sleeves; portfolio.json dated after the
valuation session → refused; computed_at = report_date + 1 → accepted, + 2 → refused; missing paper series → benchmark
"不可用"; the frozen fallback flag still works.

## Delivery
Branch `codex/weekly-report-fix`; do not commit; no network. Update STATUS and a REVIEW_QUEUE row (待核查). Report with a
sample report built from today's repo files (paths), test command + pass count, Concerns.
