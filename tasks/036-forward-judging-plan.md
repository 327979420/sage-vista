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

## Clarification 2026-10-19 (Claude, after Codex's stop) — replaces Step 3's data source; thresholds unchanged
Codex was right: `triangle15.trade()` R is gross; `outcome()["r19"]` keeps only `status`, `R`, `random_R` (gross twin mean), no
1.9 entry/exit and no per-twin detail. Also: when the rule-1.7 order never fills, `outcome()` returns early, so a filled 1.9 trade
has no `r19.random_R`. The ledger §17 and `docs/FORWARD_JUDGING_PLAN_ZH.md` now carry the dated clarification (Chinese).

The main metric stays **net R difference** (no definition change). Build it like this:
1. New `research/lab/forward_judge.py` (not frozen). A function `recompute(PX, records, outcomes, config)` that, for each record,
   calls the frozen `triangle15.trade` read-only with the same inputs `outcome()` uses for 1.9
   (`level`, `stop`, `level + 3*(level-stop)`, `hold=130`) and re-draws the twins exactly as `_twins` does: same pool rule as
   `run()` (`selection.eligible_pool` with `{**N.POOL, "exclude": flagged | N.FUNDS}`, minus the symbol), seed
   `int(sha256(rec["id"])[:8], 16)`, `random.Random(seed).sample(pool, min(30, len(pool)))`, same skips, same weekly-ATR stop
   multiple `m`, target 3.0R, hold 130, completed = win/loss/time. Keep e, x, stop, status per trade and per twin. Copy the loop
   logic into the new module; never edit frozen files (tests may set `triangle_forward.PX` to compare with `_twins`).
2. Net R = (x*(1-c) - e*(1+c)) / (e - stop), c = 0.001, both for 3W and each twin. Twin net mean = mean over completed twins.
   d = 3W net R - twin net mean. Metric = mean(d); t = mean / (sd(n-1) / sqrt(n)).
3. Reproduction gate: recomputed 3W gross R == `r19.R` and recomputed gross twin mean == `r19.random_R` (round 4). Mismatch →
   "对照不一致". Frozen `random_R` absent (1.7 never filled) → still recompute, flag "无冻结核对", count separately.
4. Counting: completed trades / checkpoints = rule-1.9 sample (same ids as `summary()["rule19_all"]`: plan go and
   `market.ok`) with `r19.status` in win/loss/time — every one, twins or not. Scored (enters mean and t): has 3W net R,
   >= 1 completed twin, no mismatch. If unscorable > 10% of completed at a checkpoint → verdict "暂停判断（对照不足）" for that
   checkpoint (no alarm 1, no "证明有效"); alarm 2 unaffected. Never drop trades to make a checkpoint.
5. Report gross R difference only as a check line labelled "毛 R 差（未扣费，仅核对用）".
6. Tests (add to the list above): net-R formula on a hand example; twin draw identical to `_twins` (assert gross mean equals the
   value from calling the frozen `_twins` on the same synthetic PX/pool); the 1.7-unfilled case; mismatch → excluded but counted;
   the 10% pause rule at a checkpoint. Engineering check allowed: on the three records `fingerprint()` builds from
   `universe-1985-v1`, gross values equal frozen `outcome()` output — equality only, report no R statistics from it.
7. Formal scoring needs the forward run's extended prices, so it must run in the forward Actions job right after
   `triangle_forward`. No `.github/` edits: put the workflow patch in your report. Status until the owner approves the patch:
   "已实现，尚不能正式计分". With 0 forward signals nothing is lost.
8. Step 2 numbers stay as a limited waiting-time estimate (net-R SD stand-in, not a power guarantee); keep its limits text.

## Deliverables
Ledger §17 entry + `docs/FORWARD_JUDGING_PLAN_ZH.md`; `research/lab/forward_judge.py` + tests; Step 2 numbers in
`work/reports/forward-sample-size-v1.{json,md}` (plain Chinese, conclusion first). Update `docs/STATUS.md` and add a
`docs/REVIEW_QUEUE.md` row (待核查). Branch `codex/forward-judging`; never merge main. Report with Concerns.
Not in scope: changing the weekly workflow (`.github/`) to call the scorecard — put a suggested patch in your report instead.
