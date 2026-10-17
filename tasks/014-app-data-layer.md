# Task 014: App phase 1 - data layer (small per-page JSON files)

Read `tasks/README.md` first. Owner decision (2026-10-17: "3好" = build the PRD Must items). PRD: `work/prd-sv-app.html` (US-1..US-5).
This card is ONLY the data the new pages will read. No page, CSS or UI change in this card (that is task 015). Do not touch
frozen code (`research/lab/triangle15.py`, `buysystem.py`, the frozen config fingerprint) or change any trading rule.

## Why
The live site ships 138 MB of public JSON (`signal-history.json` 40 MB, `unified-v2-rankings.json` 55 MB). The app pages must load
fast on a phone. Each new page reads ONE small file, built by GitHub after the existing forward record step.

## Output: `public/app/*.json`, each <= 2 MB uncompressed, `schema_version: 1`, `generated_at`, `as_of`
1. `today.json` (US-1): market light = SPY close vs its 200-day SMA, and breadth = share of the forward-record universe above their
   200-day SMA (the rule-1.8 market state, same definition `triangle_forward.py` already records - reuse it, do not redefine).
   Light: green if both hold, amber if one, red if none. Plus `this_week`: a list of plain actions derived ONLY from the files below
   (new 3W orders to place, open 3W positions near stop/target, "month-end rebalance due" when the next session starts a new month).
2. `signals.json` (US-2): every record in `research/lab/forward/triangle/signals.jsonl` for version 3w-1.9 with its order
   (limit, stop, target, R multiple), status from `outcomes.json` (waiting / open / closed with R), and `factor_tags`
   (entry tags and risk tags from `research/lab/factor_tags.py`, as context only). No anonymised blind-judging fields.
3. `portfolio.json` (US-3): the 10 sleeves (XLB XLE XLF XLI XLK XLP XLU XLV XLY SPY), each with last close, 200-day SMA, distance %,
   hold = ETF or SHY, as of the last month-end signal AND as of today (so the page can say "would switch at month end").
   Rules exactly as `work/v3w/sector_trend.py` v2 (do not import work/; re-implement the 20-line rule in the new module and test it).
   Label it `"status": "candidate"` (the PRD: "candidate" until the locked-data exam passes; task 013 decides that later).
4. `record.json` (US-5): the honest scorecard. Static facts copied from ledger section 17 into a checked-in source file
   (`research/lab/app/record_facts.json`, each fact with its ledger heading) plus live forward-record counts from `outcomes.json`.
   Never compute new backtest numbers here.

## Prices
Sector ETFs + SHY: the frozen dataset `sector-etf-1998-to-2026-10-v1` plus the EODHD bulk end-of-day files the forward step already
caches in `work/triangle-bulk` (US bulk includes ETFs). If a ticker is missing for the latest session, keep the previous close and
set `"stale": true` on that sleeve - never fail the whole run, never invent a price.

## Code and wiring
- New module `research/lab/app_data.py` (`python3 -m research.lab.app_data [--publish]`), local preview writes `work/app-data/`.
- `research-lab.yml`: one new step after "Update the weekly triangle forward record", and add the sector dataset to that step's
  cache. `--publish` commits only `public/app/` and must respect the existing 23:30-04:30 UTC window guard used by the lab runner.
- Size guard: reuse `services/scanner/public_asset_limits.py` plus a 2 MB per-file check that fails the step.
- Tests in `tests/test_app_data.py` with small fixtures in `tests/fixtures/app/` (no `work/` imports): light colours, sleeve rule at a
  month boundary, stale price, status mapping from outcomes, size guard, deterministic output (same input -> same bytes).

## Stop and ask if
the breadth definition in `triangle_forward.py` is ambiguous, the sector dataset is not reachable from Actions, any number on the
record page has no ledger source, or a field needs a new trading parameter.

## Deliverables
Code + tests + workflow change on a branch (Claude commits), a sample `work/app-data/` run from local data, codex report with
Concerns. No network, no commits.

## Decisions (2026-10-17, Claude, answering Codex's two questions before any code)
1. Homepage breadth: use `triangle_forward.market()` on `universe-1985-v1` only, reuse the existing function unchanged, and put
   `"breadth_source": "universe-1985-v1"` in `today.json`. Each signal keeps the market state of its own dataset. No merging or averaging.
2. Open positions: output only the distance to stop and to target (in % and in R). No "near" judgement and no alert threshold in this
   card. `this_week` lists new orders to place and the month-end rebalance only. Any threshold is a later product decision for the owner.
