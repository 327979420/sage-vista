# Task 048 — Forward record: an "executable" column next to rule 1.9 (SV-66)

Read `tasks/README.md`, ledger section 17 entry **"2026-10-29 Task048"** (the definition is fixed there — implement it exactly),
`research/lab/triangle15.py` (`signals`, `trade`), `research/lab/triangle_forward.py` (`run`, `outcome`, `summary`),
`research/lab/forward_judge.py` (`cached_prices`, `recompute`), `research/lab/paper.py` (`write`/`publish` pattern),
`research/lab/app_data.py` (forward data) and `app/forward/`. Owner approved 2026-10-29.

Why: the scanner first sees a 3W signal only after the first session of the week after next, but the frozen replay places the
limit order from the signal day. The owner wants a side column that shows what they can actually trade. **Frozen code stays
untouched** (`triangle15.py`, `triangle_forward.py`, `research/lab/forward/`, `paper.py`): the fingerprint must not change.

## Build
1. New module `research/lab/forward_exec.py` (import the frozen modules read-only; no second trade engine):
   - `live_day(dates, signal_idx, recorded_at=None)` → index L per the ledger (session after the first session of the week after
     next; pushed later when `recorded_at` is after 09:30 ET of that session). Use the NYSE dates in the series itself.
   - `executable(series, signal_idx, plan, recorded_at=None)` → `{"status", "live", "R"?, "fill"?, "exit"?}`. Statuses:
     `skip_stop`, `skip_target` (pre-live window checks, stop first), then whatever `triangle15.trade(series, L-1, level, stop,
     level + 3R, hold=130, wait=40-(L-1-signal_idx))` returns. R = net R (0.1% per side, actual fill risk), as the judge computes.
   - `--history`: all five datasets of the forward config, signals 2005-01-01..2024-06-30, plan go and market ok (market state as
     `triangle_forward.market` computes it, per dataset like `run`), print as-recorded vs executable counts and mean net R.
     **Must reproduce** the ledger reference: 571 trades +0.244R vs 484 trades +0.262R (Claude's script:
     `work/reports/lag-2026-10-29/compare.py`; your numbers must match to the trade; if not, stop and report why).
   - default run: for every forward record (signals.jsonl) with plan go and market ok, compute the column from the same local
     caches the forward step used (`forward_judge.cached_prices`, capped at outcomes `computed_at` date); write
     `research/lab/forward_exec/latest.json` = `{schema_version, version "3w-1.9", computed_at, outcomes_computed_at,
     rows: [{id, symbol, live, status, R?}], summary: {trades, wins, mean_R, sum_R, skipped_stop, skipped_target, waiting, open}}`.
     Closed = win/loss/time, as in `summary`. Missing price → stop with an error, never guess. `--publish` commits only that
     folder, the way `paper.publish` does (refuse inside the EOD window).
2. Workflow: one step right after "Update the weekly triangle forward record", `continue-on-error: true`,
   `python3 -m research.lab.forward_exec --publish`. Nothing else in `.github/` changes.
3. Public /forward page: `app_data` adds a whitelisted `executable` block (summary fields only plus `computed_at`; refuse a file
   whose `outcomes_computed_at` differs from the forward outcomes it shows) to `public/app/forward.json`; the page shows one row
   beside the rule-1.9 summary: 「实际能做到（信号认出后才挂单）」 with trades / mean net R, and "暂无" when absent. Add the English
   entry to `app/i18n/catalog.ts`. No other page or number changes.

## Tests
`live_day` on a normal week, a Monday-holiday week and a late `recorded_at`; pre-live stop → `skip_stop`; pre-live target →
`skip_target`; both on one day → `skip_stop`; a pre-live dip below the limit fills at the live session's open; the 40-session
window counted from the signal day; the frozen fingerprint unchanged (`python3 -m research.lab.triangle_forward --fingerprint`
equals config); app_data refuses a mismatched `outcomes_computed_at`; page test for the new row. Existing tests stay green.

## Delivery
Branch `claude/forward-executable` (already checked out here); do not commit; no network. STATUS + a REVIEW_QUEUE row (待核查).
Report: `--history` output vs the reference, test commands + pass counts, Concerns.
