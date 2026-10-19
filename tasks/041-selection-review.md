# Task 041 — Selection review page: what pulls the owner toward the wrong picks

Read `tasks/README.md`, `tasks/038-owner-eye-and-own-picks.md` and `work/v3w/mixed035/MAINTAINING.md`. Owner asked 2026-10-19
after the first pooled eye verdict (184 revealed answers: picked cases −0.23R, skipped cases +0.23R, do−no −0.46R,
95% CI −0.98 to +0.07, "未证明"). Goal: let the owner SEE their own selection habits. This describes the owner; it never
changes the frozen 3w-1.9, never proposes a trading rule, and is not research on old data (ADR-16).

## Fixed (do not change)
- Inputs: the three banks and keys (daily1, mixed1, hk1) and the answer exports Claude puts in
  `work/v3w/review041-inputs/{daily1,mixed1,hk1}/` (read-only). Only revealed answers count (each page's batch rule).
  Never touch the trainer pages, banks, keys or any real database.
- Four groups: 做了·赚 / 做了·亏 / 跳过·赚 / 跳过·亏 (win = net R > 0). The page leads with the two "mistake" groups side by
  side: 做了·亏 vs 跳过·赚.
- Each case card: the original blind chart (same SVG as the trainer) + the later-move view, then ticker, market, timeframe,
  dates, net R, the owner's confidence, "shape wrong" mark and note. Reuse the shared chart code; no forked chart renderer.
- Feature table, PRE-FIXED list only (no search over other features, no thresholds, no p-values, no "rule" wording):
  1. timeframe; 2. confidence 1/2/3; 3. "shape wrong" mark; 4. run-up before the signal (% change over the 26 bars before the
  signal bar); 5. distance of the signal close from EMA20 (in signal-bar ATR); 6. pattern depth (highest push to lowest
  bottom, %); 7. signal-bar volume / mean volume of the previous 20 bars; 8. planned R:R. All computed only from the bars
  visible in the blind chart. Show each feature's median per group (n shown), plus a small dot strip per feature.
- Plain Chinese, one-line header: "这页只描述你的选择习惯，不是交易规则。" Mention sample sizes everywhere; groups under 10
  cases get "样本太少".
- Build is a script that can be re-run when the owner finishes more questions (Claude refreshes the exports and rebuilds).

## Acceptance (Claude checks)
1. Group counts equal the eye scorecard (`research/lab/eye_judge.py`) for the same exports.
2. Three sampled cases: chart, net R and features recomputed independently and matching.
3. No feature outside the fixed list; no statistical test or threshold text in the page.
4. Trainer pages, banks and keys byte-identical (hashes before/after).
5. Tests pass; 390 px and 1440 px rendering checked by Claude.

## Deliverables
Page `work/site-v2/selection-review-1.html`, private scripts `work/v3w/review041/` + tests. Ledger §17 note (descriptive
owner review, no new research), `docs/STATUS.md`, a `docs/REVIEW_QUEUE.md` row (待核查). Branch `codex/eye-review`; do not
commit; never `git add -f work/`. Claude publishes.
