# Task 036 — How the forward record will be judged (pre-registration + scorecard)

Read `tasks/README.md` first. Owner asked 2026-10-19 (via Claude). ADR-16 run-and-record mode: this card adds NO rule, NO variant
and NO tuning. It fixes, before any forward signal exists (0 signals at 2026-10-18), how the forward record of the frozen `3w-1.9`
and the paper account will be read, so nobody explains results after seeing them.

## Step 1 — Pre-register (do this first, before writing code)
Copy the block "预登记" below verbatim into `docs/CASE_REVIEW_LEDGER_ZH.md` section 17, dated 2026-10-19, and into a new
`docs/FORWARD_JUDGING_PLAN_ZH.md`. Do not change any number. If a number looks wrong, stop and ask.

### 预登记（前向记录判卷规则，2026-10-19 写定，结果出来前）
- **主指标**：冻结 3w-1.9（规则 1.9）全部已结束交易的「每笔净 R − 同日 30 只随机孪生的平均 R」，即 `triangle_forward` 已算的随机对照。
- **检查点**：已结束交易满 30、60、100 笔，以及之后每满 100 笔；另每年 10 月做一次描述性年报。检查点之间只记录，不下结论。
- **失效警报（任一触发 → 模拟账户暂停新 3W 卫星仓，由 owner 决定）**：
  1. 任一检查点（≥30 笔）主指标均值 < 0 且 t ≤ −2.0；
  2. 卫星（3W）部分的模拟账户从高点回撤 > 25%（历史最大回撤 24.8%）。
- **「证明有效」**：只在 ≥100 笔的检查点判断，需同时满足：主指标 t ≥ 2.0；且同期 3W 卫星账户 Sharpe ≥ SPY 同期 Sharpe。未满 100 笔不得写「有效」。
- **其余情况**：写「继续记录，未证明」。
- **始终同时报告**：笔数、胜率、盈亏比、profit factor、平均 R、随机对照、账户收益/回撤，以及核心（行业趋势）、卫星、合计三部分各自对 SPY。
- **不因前向结果改规则**。任何规则修改 = 新版本、新开始日期、旧记录照旧继续。
- 样本估算（第 2 步算出）只用于告诉 owner 要等多久，不改变以上门槛。

## Step 2 — How long will it take? (descriptive, existing results only)
Use only results that already exist for the frozen 3w-1.9 (Task 002 baseline candidates `w3_cands.json`, the US validation
2005-01..2025-06 on the five frozen datasets). No new scans, no variants.
1. Historical completed trades per year (rule 1.9, account-taken trades and all candidate orders separately).
2. Per-trade SD of (net R − same-day twin mean R); if twin R per trade is not stored, use the per-trade net R SD and say so.
3. Trades needed for t = 2.0 at a true edge of +0.07R (the measured selection edge), +0.15R and +0.30R; convert to years at the
   historical rate. Report also the chance of a false "失效警报 1" at 30 trades if the true edge is +0.07R (simple normal approx).

## Step 3 — Scorecard code
- New `research/lab/forward_judge.py` (NOT inside `research/lab/forward/`, which is frozen). It reads
  `research/lab/forward/triangle/outcomes.json` (and `signals.jsonl` for dates) and writes `work/forward-judge/latest.json` and
  a short Chinese `latest.md`: completed trades, next checkpoint and how many trades to go, the main metric with t, alarm 1 state,
  and the always-report list above. Alarm 2 and the SPY comparison take the paper account as an input file
  (`--paper path.json`, format: daily `{date, core, satellite, total, spy}` values); missing file → "未提供", never guessed.
- If `outcomes.json` lacks a per-trade field you need (e.g. twin mean R per trade), stop and report; do not edit the frozen
  forward code.
- Tests in `tests/test_forward_judge.py` on synthetic outcomes: 0 trades; 29 vs 30 trades (checkpoint boundary); alarm 1 fires
  only at a checkpoint and only with mean < 0 and t ≤ −2; "证明有效" impossible below 100 trades; alarm 2 at >25% satellite
  drawdown; missing paper file.

## Deliverables
Ledger §17 entry + `docs/FORWARD_JUDGING_PLAN_ZH.md`; `research/lab/forward_judge.py` + tests; Step 2 numbers in
`work/reports/forward-sample-size-v1.{json,md}` (plain Chinese, conclusion first). Update `docs/STATUS.md` and add a
`docs/REVIEW_QUEUE.md` row (待核查). Branch `codex/forward-judging`; never merge main. Report with Concerns.
Not in scope: changing the weekly workflow (`.github/`) to call the scorecard — put a suggested patch in your report instead.
