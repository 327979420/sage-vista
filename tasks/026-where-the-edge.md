# Task 026: where does 3W's edge come from, and is the owner's eye better than random? (description + one pre-registered test)

Read `tasks/README.md` first. Owner (2026-10-18): "start the next research step, record it in the ledger, I want to see good or bad."
Background: research standard v1 calibration (task 024) - on US development data, 3W signals beat same-day random twins by only
+0.07R (week-bootstrap p 0.19), while the account-level test looked better. Development data is overfit-prone: everything here is
DESCRIPTION, except the single pre-registered test in Part B. No rule changes, no new versions.

## Part A - decomposition on US development data (description only)
Using the task-024 machinery (event level, merged US pool, frozen order/exit, US cost 0.1%, week bootstrap for CIs), report mean R per
event and 95% CI for these pre-listed variants, each changing ONE component:
A1 frozen 3W as is (baseline = task 024).
A2 same signals, market filter OFF (signals the filter blocked are added back).
A3 same signals, entry at next open instead of the 2% limit.
A4 same signals, exit = hold 13 weeks (no stop/target) instead of stop + 3R + 26 weeks.
A5 random twins with the frozen order/exit (= task 024 twins).
A6 random twins, market filter OFF.
A7 random twins, entry at next open, hold 13 weeks, market filter ON (random stocks with changed entry and exit rules).
Then the contribution table: selection (A1-A5), market filter (A1-A2 and A5-A6), entry rule (A1-A3), exit rule (A1-A4), and
"rules on random stocks" (A5-A7). Exactly these 7, nothing added after seeing results.

## Part B - the owner's eye (ONE pre-registered test)
Data: `research/lab/cases/3w-user-decisions-2026-10.json` (blind decisions) + the key file kept locally
(`work/v3w/3w-blind-keys-2026-10.json`, check its SHA-256 against `keys_sha256`). For every decided case, the frozen trade's R (or the
same order on the case even if it was not a frozen-1.9 signal - state which, per case) and its 30 random twins.
Primary test (registered now): d = mean R(做) - mean R(不做); one-sided week-block bootstrap (10,000, seed 20261019); the owner's eye
"adds value" if d > 0 and p <= 0.05. Also describe: 做 vs twins, 不做 vs twins, by confidence level if recorded, and the taste model
score vs outcome (description only - the taste model was fitted on these decisions, so it is in-sample).
Caveats to state: decisions span development data and later new data; some cases fed the taste model.

## Deliverables
`work/v3w/where_edge.py` + log, `work/reports/where-edge-v1.{json,html}` (simple Chinese, inline SVG: contribution bars, 做/不做 bars
with CIs), codex report with Concerns. Stop and ask if any definition is ambiguous. No network, no commits.

## Decisions (Claude, 2026-10-18, fixed before any task-026 result)
1. Use all 207 blind decisions; prices run to the latest date in the local datasets. The primary test uses only CLOSED trades (stop, 3R target, or 26-week exit). Open and unfilled cases are counts/description only. Report the before-2025-07 and from-2025-07 split as description only; do not restrict the primary test to the 33 earlier cases. Decisions span development data and later new data.
2. Keep task 024's established exception: pre-2005 bars only for warm-up and frozen cooldown state; retain the original full-history bad-jump filter. US 1985-2004 is no longer locked (task 013). Never load HK group B.
3. A7 retains the market filter, so A5-A7 compares entry and exit rules only.
