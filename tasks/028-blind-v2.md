# Task 028: blind test v2 question bank (100 trade-eligible cases) + answer page

Read `tasks/README.md` first. Owner (2026-10-18): keep doing blind tests to prove the eye; NO sector/industry shown; time shuffled.

## Cases
100 cases, all of which the frozen 3w-1.9 rule WOULD have ordered and that filled (so every answer becomes a scored trade):
- from US development data trades the owner has NOT judged before (exclude every case in `3w-user-decisions-2026-10.json` and
  `triangle-user-judgements-2026-10.json`, matched by symbol + signal week via the local keys), and
- all eligible HK group A trades (~35). Never HK group B.
Mix and shuffle with seed 20261020. Hide symbol, dates, prices' absolute level (rebase the chart to 100 at the signal close) and the
market. Show: weekly candles (~60 weeks to the signal week), MACD pane, the push line and bottoms as on the ticket page, the order
(limit / stop / target as % from the signal close). Keep an answer key file locally (`work/v3w/blind-v2-keys.json`, SHA-256 in the bank).

## Page
One self-contained HTML (`work/site-v2/blind-v2.html`) in the site's theme: one case at a time, big chart, buttons 做 / 不做, optional
confidence 1-3 and a note, progress "12 / 100", keyboard shortcuts (D / N, arrows). Answers are stored through the artifact db
capability (Claude publishes it): collection `blindv2`, doc id = case id, fields {choice, confidence, note, answered_at}; first answer
per case is final (show it as locked). No outcome is shown until the owner finishes all 100.
Use `window.claude.use("db")` exactly as `work/` earlier blind pages did if one exists; otherwise follow the pattern: on load, read
existing answers; on click, `set` the doc. Handle db = null by keeping answers in memory and showing a warning.

## Pre-registration (write into ledger section 17 before generating)
Eye test v2 primary: on these 100 new decisions, d = mean R(做) - mean R(不做) of the frozen trades; one-sided week-block bootstrap
(10,000, seed 20261021); PASS if d > 0 and p <= 0.05. Pooled with the task-026 cases: description only.

Deliverables: generator script + log, the bank JSON (no keys), the page, codex report. Staging dir `task028-staging/` if work/ is not
writable. No network, no commits.
