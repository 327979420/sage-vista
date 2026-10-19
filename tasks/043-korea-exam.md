# Task 043 — The frozen 3W (3w-1.9) sits a Korea exam once (replaces Task 037)

Read `tasks/README.md`, `tasks/010-hk-exam.md` and `tasks/037-japan-exam.md` (this card copies 037's flow and lessons).
Owner decided 2026-10-19: Japan is not in the EODHD plan (probe run 39234457098 lists 70 exchanges, none in Japan), so the
overseas exam moves to Korea — KRX main board `KO` plus KOSDAQ `KQ`. Task 037 is closed without any Japan data; its parked
spec stays in `research/lab/queue-parked/`. This tests the frozen rules on a market never used; NOT a new variant (ADR-16).

Network work runs only on GitHub Actions (Claude triggers it). Three STOP points — stop there, report, wait.

## Step 1 — Pre-register and prepare the universe screen (local)
1. Add `#kr-exam` to `docs/rules/08` and a ledger §17 entry "3W 韩股考试（2026-10-19 登记，看到任何韩股数据前）" with the fixed
   values below, verbatim. Note there that 037 (Japan) is closed because the provider has no Japan coverage.
2. Fixed values (do not change):
   - Exchanges: EODHD `KO` and `KQ`, screened as ONE universe. Provider Type == "Common Stock" only, listed and delisted;
     tickers in both the listed and delisted list of the same exchange left out (reused codes).
   - Company key = the 6-character code (suffix after "." removed). A company listed on both KO and KQ over time (board move)
     keeps the listing with the most valid daily bars in 2005-01-01..2025-06-30 (tie -> KO); dedupe before the liquidity screen.
   - Preferred shares: KRX common-share codes end in "0"; exclude any code whose 6th character is not "0" (preferred and other
     classes), counted as "非普通股代码".
   - Name exclusions (case-insensitive): ETF, ETN, REIT, FUND, INDEX, SPAC, ACQUISITION, KODEX, TIGER, 스팩, 리츠. Count each.
     Review flag only (not an exclusion): list every kept name containing PREF, 우, HOLDINGS or 지주 for Claude at STOP 2.
   - Korea pool (US pool translated, fixed before any Korea data): unadjusted close ≥ ₩1,000; ≥ ₩13 billion traded per day
     (≈ US$10M at 1,300 KRW/USD); min_sessions 60 in 2005-01..2025-06; min_history 420 as HK.
   - Market proxy: KODEX 200 ETF `069500` (KO), replacing SPY in the market filter (same code path as HK's 2800); never a
     candidate. Exclude a candidate whose signal, fill or exit day is not a 069500 session.
   - Cost 0.2% per side (same as HK; covers the sell-side transaction tax).
   - Group split: if more than 2,000 companies are kept, split A/B like ADR-2 (sorted, `random.Random(20261019)`, A = first
     ceil(n/2)); B LOCKED. Otherwise use all.
   - Pre-2005 prices: indicator warm-up only.
   - Known limitation (report, do not model): daily price limits (±15% before 2015-06-15, ±30% after) can make a stop
     unfillable at the stop price on a limit-down day; the frozen daily-OHLC fill rules are kept unchanged.
3. `research/lab/queue/data-kr-universe-v1.json` modelled on the Japan spec (kind `screen`, exchanges `["KO", "KQ"]`,
   fetch_start 2004-01-01, shard_prefix `kr-2005-2025-v1`, max_error_share 0.02, min_kept 300). Extend `screen.py` for a list of
   exchanges where needed, keeping US/HK/TSE behaviour byte-identical (show it), with unit tests for the Korea filters,
   cross-board dedupe and the code-class rule.

**STOP 1** — report; Claude reviews, merges and triggers the screen.

## Step 2 — Freeze the dataset (after the screen passes and Claude reviews the flags)
`research/lab/queue/data-kr-a-v1.json`: dataset `kr-a-1995-v1` (group A, or all) + `069500`, daily from 1995, `keep_raw: true`,
max_missing_share 0.05. **STOP 2.**

## Step 3 — The exam (local, once)
As Task 010/037: frozen pipeline, signals 2005-01-01..2024-06-30, accounts marked to 2025-06-30; 100,000 start, 2% risk,
20% cap, 10 positions, 10% heat; 1,000 random accounts (same-day random Korea-pool stock per taken signal); benchmarks 069500
buy-and-hold and 069500 at 3W's daily invested share.
**Verdict (pre-registered):** PASS if full-period Sharpe p ≤ 0.05 vs random AND at least 100 trades; under 100 trades
"样本不足，未证明". Everything else descriptive; always report win rate, payoff, profit factor, mean R, exposure, max drawdown.
**STOP 3** — a bug found before final numbers stops the run; never rerun after seeing results.

## Deliverables
rules/08 + ledger; queue specs; code + tests; `work/v3w/kr_exam.py` + log; `work/reports/kr-exam-v1.{json,html}` (plain
Chinese, inline SVG). STATUS + REVIEW_QUEUE (待核查). Branch `codex/kr-exam`; never merge main; no `.github/` edits; do not
commit. Concerns: survivorship (delisted coverage), price limits, KOSDAQ small caps, proxy fit.

Amendment (Claude, 2026-10-19, before any Korea data was seen): a provider code that is not six characters is excluded and counted as "代码格式异常" instead of stopping the screen.
