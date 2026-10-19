# Task 037 — The frozen 3W (3w-1.9) sits a Japan exam once

Read `tasks/README.md` first, then `tasks/010-hk-exam.md` (the Hong Kong exam): this card copies it. Owner asked 2026-10-19
(via Claude). This is a test of the frozen rules on a market never used, NOT a new variant (allowed under ADR-16: no mining).
HK lesson: 441 stocks gave only 14 trades, so the result could only say "not proven". Japan is chosen for its size.

Network work (EODHD) runs only on GitHub Actions. You prepare specs and code; Claude/the owner triggers the runs. The card has
three STOP points — stop there, report, and wait.

## Step 1 — Pre-register and prepare the universe screen (local)
1. Add `#jp-exam` to `docs/rules/08` (same layout as `#hk-exam`) and a ledger §17 entry "3W 日股考试（2026-10-19 登记，看到任何日股数据前）"
   with the fixed values below, verbatim.
2. Fixed values (do not change):
   - Exchange: EODHD `TSE` (Tokyo). Common stocks only, listed and delisted; tickers in both lists left out (reused codes);
     ETFs/REITs/funds are never candidates.
   - Japan pool (US pool translated, fixed before seeing data): unadjusted close ≥ ¥100; ≥ ¥1.5 billion traded per day
     (≈ US$10M at 150 JPY/USD); min_sessions 60 in 2005-01..2025-06; same min_history 420 as HK.
   - Market proxy: NEXT FUNDS TOPIX ETF `1306` (replaces SPY in the market filter, same code path as HK's 2800).
   - Cost 0.2% per side (same as HK).
   - Group split: if more than 2,000 stocks are kept, split A/B exactly like ADR-2 (sorted list, `random.Random(20261019)`,
     A = first ceil(n/2)); B is LOCKED. If 2,000 or fewer, use all of them (no B group). Fixed now, before counts are seen.
   - Pre-2005 Japan prices: indicator warm-up only.
   - Lessons from the HK bank (Task 039, 2026-10-19): one code per company (company key = code without suffix, leading zeros
     stripped; keep the code with the most sessions), and exclude anything the provider does not type as "Common Stock" plus
     any code a TSE code range marks as ETF/ETN/REIT/fund. Exclude a candidate whose signal, fill or exit day is not a 1306
     session (no look-ahead in the market filter). Report each exclusion count. Fixed now, before any Japan data is seen.
3. Write `research/lab/queue/data-jp-universe-v1.json` modelled on `data-hk-universe-v1.json` (kind `screen`, exchange `TSE`,
   fetch_start 2004-01-01, shard_prefix `jp-2005-2025-v1`, criteria max_error_share 0.02, min_kept 300).
4. Check `services/scanner/eodhd.py` and the dataset builder handle `TSE` symbols (numeric codes, any suffix rules). Only add
   what is missing, keep the default US/HK behaviour unchanged, unit tests for the new path. If the change goes beyond an
   exchange parameter, stop and ask.

## Claude answers (2026-10-19; before any Japan data is seen)

These replace the code-range exclusion and clarify the dedupe rule in the original HK-lessons bullet above; all other fixed values remain unchanged.

1. Non-common stocks: I cannot verify a complete official TSE code-range list offline, so NO code-range exclusion. Rule instead, fixed now: keep only provider Type == "Common Stock", and additionally exclude any symbol whose provider Name contains (case-insensitive) ETF, ETN, REIT, FUND, TRUST, INDEX, 投資法人, 上場投信, ファンド, 指数. Count each exclusion. Then, as a review flag only (not an exclusion), list every kept code in 1300-1699, 2500-2599 or 8950-8999 with its provider name in the screen report; Claude reviews that list at STOP 2 before the dataset is frozen, and any change is a dated note made before any price is used for signals.
2. Dedupe window: count valid daily bars in 2005-01-01..2025-06-30; tie -> lexicographically smallest code; dedupe runs before the liquidity screen. Company key = code without suffix after "." or "-", leading zeros stripped.
   Amendment (Claude, 2026-10-19, before any Japan data was seen): "TRUST" is removed from the name exclusions, because it would drop real common stocks such as trust banks (e.g. Sumitomo Mitsui Trust Holdings). The other terms stand.

**STOP 1** — report; Claude reviews and triggers the research-lab run.

## Step 2 — Freeze the dataset (after the screen passes)
`research/lab/queue/data-jp-a-v1.json` modelled on `data-hk-a-v1.json`: dataset `jp-a-1995-v1` (group A, or all if no split)
+ `1306`, daily from 1995, `keep_raw: true`, criterion max_missing_share 0.05. If the screen failed its criteria, stop and report.

**STOP 2** — report; Claude triggers the build.

## Step 3 — The exam (local, once)
Exactly as Task 010 with the Japan values: frozen pipeline (`work/v3w/fair19.py` path), signals 2005-01-01..2024-06-30, account
and random accounts marked to 2025-06-30; 100,000 start, 2% risk, 20% cap, 10 positions, 10% heat; 1,000 random accounts (same-day
random Japan-pool stock per taken signal); benchmarks 1306 buy-and-hold and 1306 at 3W's daily invested share.

**Pre-registered verdict**: PASS if full-period Sharpe p ≤ 0.05 vs random **and** at least 100 trades. Under 100 trades the
verdict is "样本不足，未证明" whatever p is. Everything else (CAGR, decades, vs 1306) is descriptive.
Always report win rate, payoff ratio, profit factor, mean R, exposure, max drawdown.

**STOP 3** — if you find a bug before the final numbers, stop and report; do not rerun after seeing results.

## Deliverables
rules/08 + ledger entries; queue specs; code + tests; `work/v3w/jp_exam.py` + `.log`; `work/reports/jp-exam-v1.{json,html}` (plain
Chinese, inline SVG, no pre-2005 results, no group-B symbols). Update `docs/STATUS.md`, add a `docs/REVIEW_QUEUE.md` row (待核查).
Branch `codex/jp-exam`; never merge main. No `.github/` edits. Report with Concerns (survivorship: delisted coverage; split
adjustment; the TOPIX ETF as proxy).
