# Task 042 — Automatic trade review (machine post-mortems)

Read `tasks/README.md`, `tasks/036-forward-judging-plan.md`, `tasks/038-owner-eye-and-own-picks.md`. Owner decided 2026-10-19
(workbench ADR-17) after 214 blind training answers showed no proven benefit from hand-filtering: 3W runs mechanically and
the machine, not the owner, writes the reviews. This card adds NO rule, NO variant and NO tuning (ADR-16); it only explains
what happened to each trade, the same way every time.

## What gets reviewed
Every trade that closes (win / loss / time) in:
1. the frozen 3W forward record (`research/lab/forward/triangle/` + `research/lab/forward_judge.py` recompute);
2. the owner's own picks (`research/lab/own_picks/`);
3. the cockpit accounts — `paper` and `real` — from a JSON export Claude provides
   (`positions` rows: account, symbol, source 3W|core|manual, qty, entry, stop, target, opened, status, last, exit_price).

## One review card per closed trade (fixed fields, plain Chinese)
- Plan vs actual: planned entry / stop / target vs actual fill and exit; entry slippage in % and in R; exit reason
  (stop, target, time, manual).
- Result: net R (cost 0.1% per side), holding days, max favourable and max adverse excursion in R during the hold.
- Context: same-day random twins' net R (from the 036/038 recompute where it exists), SPY return over the same days.
- Rule check, mechanical: for 3W/paper trades, did the trade follow the frozen order (limit, stop, 3R, 26 weeks)? For the real
  account, list each deviation from the matching 3W alert (skipped, different price, moved stop, early exit) — record only,
  no judgement words.
- Chart: daily bars from 60 sessions before entry to 20 after exit, with entry, stop, target and exit marked.

## Weekly digest
`work/trade-review/weekly-YYYY-MM-DD.html`: trades closed this week, running totals per source (count, win rate, payoff,
profit factor, mean net R, vs twins), and the list of real-account deviations with their R impact (actual R minus the R the
alert would have produced). No advice, no rule proposals.

## Fixed
- Read-only use of frozen code and records; no edits to `research/lab/forward/`, `triangle15.py`, `triangle_forward.py`.
- Missing data → the field says "缺数据", never a guess. No network in the sandbox; offline caches only.
- Tests on synthetic trades: each exit reason; gap through stop; slippage sign; MFE/MAE; deviation detection for each kind;
  a trade with no twins; empty week.

## Deliverables
`research/lab/trade_review.py` + tests; sample digest built from synthetic data; ledger §17 note; `docs/STATUS.md`,
`docs/REVIEW_QUEUE.md` row (待核查). Suggested Actions step (weekly, after the forward scoring) as a patch in the report —
not applied. Branch `codex/trade-review`; do not commit; never `git add -f work/`.
