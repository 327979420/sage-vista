# Task 003: decision-layer diagnostics (descriptive only; no rule is chosen here)

Read `tasks/README.md` first (you are the second expert: stop and ask if anything is unclear). Pre-registered in ledger section 17
("组合决策层·诊断").

## Why
The owner wants a portfolio decision layer on top of 3W: sector balance, "which signal gets the slot", and "when full and a better
signal arrives, what do we sell". Task 002 found 269 of 571 3W signals never enter the account. Before designing any rule we need to
know how much there is to gain and where concentration hurts. Nothing here becomes a rule.

## Inputs
`work/v3w/w3_cands.json` (task 002 cache; 571 candidates, calendar) and the baseline account exactly as task 002 (`book()` in
`work/v3w/reality3w.py`, cost 0.1%). Sectors: `data/industry/nasdaq-industry-2026-08-25.json` (a 2026 snapshot; delisted stocks are
mostly missing -> label "UNKNOWN"; never guess a sector).

## Steps
1. Taken vs skipped. Mark each signal taken/skipped by the baseline account and the skip reason. For every signal compute its
   standalone trade R from its own fills (entry, stop, fills; same definition as task 002's D but standalone, before account fees).
   Report count, mean R, median R, win rate, for taken and skipped, overall and for 2005-2014 / 2015-2025.
2. Room for selection (upper and lower bounds, look-ahead on purpose, label them as such). Run the account with priority = best
   realised R first ("oracle") and worst first ("anti-oracle"). Report CAGR / Sharpe / max drawdown next to task 002's 200-random
   median and P10/P90. These are bounds, not strategies.
3. Sector exposure of the baseline account: daily share of invested capital by sector (UNKNOWN shown separately); average and maximum
   share per sector; number of days any single known sector is >= 40% of invested capital; the 5 worst drawdowns with the sector
   mix at their peaks.
4. Pre-entry features of taken vs skipped (descriptive): planned reward/risk to target, stop distance %, ADV20 rank, sector, month.
   Only data known at entry.

## Answers to Codex's questions (2026-10-16)
1. Agreed: oracle / anti-oracle are not strict bounds (holding time, capital use and later opportunities matter). Run them as
   specified but call them "hindsight-ordering scenarios" (事后排序情景) everywhere, and say they are neither bounds nor strategies.
2. Agreed: the 2026 sector snapshot is not information known at entry. Use it only for after-the-fact description (steps 3 and 4),
   label it so, and never present sector as a pre-entry feature. UNKNOWN stays UNKNOWN.
3. ADV20 rank: same-day candidates are too few (often 1-3), so rank each signal's ADV20 (20 sessions before entry) as a percentile
   within that entry day's eligible pool (`selection.eligible_pool` with the same rules the baseline builder uses), each pool stock's
   ADV also from its 20 sessions before that day. If that pool is too expensive to build, stop and say so rather than substitute.

## Deliverables
`work/v3w/decision_diag.py` + `.log`; `work/reports/decision-diag-v1.json` and `.html` (simple Chinese, inline SVG: bar chart of mean R
taken vs skipped; sector share over time as a stacked area; a table of bounds vs random); `work/reports/decision-diag-v1-codex-report.md`
with a "Concerns" section. Tests: put no test file in `tests/` that imports `work/` (it breaks CI); a self-check inside the script is fine.

## Forbidden
Same as task 002 (same data boundary: warm-up allowed; no signal/trade/statistic before 2005-01-01 or after 2025-06-30; no HK).
No rule selection, no tuning, no commits, no network.
