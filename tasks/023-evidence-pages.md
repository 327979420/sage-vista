# Task 023: 信号凭证 + 前向记录 pages (site, branch preview first)

Read `tasks/README.md` first. Owner decisions (2026-10-18): build the evidence first; the prototype is the standard. Prototype:
`work/site-v2/sv-dashboard-prototype.html` (page "信号凭证": header chips, checklist with values, order, outcome steps, the weekly
candlestick evidence chart with 推 1-3 / 底 1-2 / 信号 markers, dashed push line, price lines, MACD pane synced below). Keep the live
site's theme and nav (phase A). The real account is NOT on the public site (ADR-14).

## Data (extend `research/lab/app_data.py`, same publish step and guards)
- Tickets exist (task 022: `public/app/tickets/`).
- New `public/app/forward.json` from the forward record (`research/lab/forward/triangle/`): per 3w-1.9 signal - symbol (or blind id),
  signal week, status, the stock's move after 1 / 4 / 13 weeks from the signal close, hit target / stop / time exit, R; the same for its
  30 random twins (median and the share the signal beat); cumulative R over time; the owner's blind call (做 / 不做) and whether it was
  right, where recorded. Add the backtest expectation for comparison as a fact copied from the ledger (average R per trade, win rate),
  with its ledger heading. < 2 MB. Tests with fixtures (0 signals; waiting; closed win; closed loss; blind call present/absent).

## Pages
1. `/signals`: list of tickets (this week first, then history; status chips) + detail view = the prototype ticket. Evidence chart with
   TradingView Lightweight Charts (pin an exact version as a dependency; no CDN). When there are 0 real signals, say so plainly and show
   one historical example ticket clearly marked 历史示例 (from the task-022 examples, generated at build time, not hand-written).
2. `/forward`: summary tiles (signals so far, closed, average R vs backtest expectation, beat-random share), cumulative-R chart, the
   per-signal table (1/4/13-week moves, outcome, vs random, blind call), and a calm empty state while there are 0 signals that says
   when the next check happens (every Friday close).
Replace the "coming soon" for 3W 机会 with these. Phone layout per the prototype (charts stack; table scrolls in its own container).

## Quality
lint, typecheck, build, node + Python tests; the preview workflow's automatic screenshots must include /signals and /forward at 1440 and
390 (add them to the page list). No production deploy. No network, no commits. Stop and ask before inventing a visual pattern that is
neither in the prototype nor on the live site. Report: files, data schema, tests, Concerns.

## Decisions (2026-10-18, Claude, answering Codex before any code)
1. `lightweight-charts@4.1.3` is installed (exact pin in package.json; Claude ran npm with network).
2. Random twins: reproduce the frozen sampling (same seeds and code path as `triangle_forward.py`) in the new projection to get each
   twin's R, then the median and the share the signal beat. Cross-check the reproduced mean R against the recorded mean for every
   signal; on any mismatch publish median/share as null with `"twins": "unverified"` and report it.
3. Blind call scoring (defined now, before any real signal exists): 做 is right if the closed trade's R > 0; 不做 is right if R <= 0;
   signals never filled or still open are "not yet scored". Show the rule under the table. The owner may change it later.
