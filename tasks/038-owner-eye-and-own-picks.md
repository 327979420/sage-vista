# Task 038 — Judge the owner's eye, and forward-record the owner's own picks

Read `tasks/README.md` and Task 036 first (this card reuses 036's checkpoints). Owner asked 2026-10-19 (via Claude).
This tests the OWNER, not the system: nothing here changes the frozen 3w-1.9, the paper account or any trainer page.
Do not touch the trainer pages, banks or cloud answers of Task 033 (`daily1`) or Task 035 (`mixed1`).

## Step 1 — Pre-register (before code; copy verbatim into ledger §17, dated 2026-10-19)

### 预登记（owner 眼光与自选股判定规则，2026-10-19 写定）
**A. 训练眼光（033 日线 daily1、035 混合周期 mixed1、039 港股 hk1，各自单独描述，结论用合计）**
- 指标：已揭晓题中，选「做」的平均净 R − 选「不做」的平均净 R（同一题库自带的冻结交易结果）。
- 结论只用三套题合计（已揭晓 ≥ 100 题时才下）；每套题单独只描述，题数不足 100 的标「样本太少，仅供参考」（mixed1 只有 80 题、hk1 只有 34 题，永远单独到不了 100）。（2026-10-19 Claude 补充，原因：题库实际题数。）
- 「眼光有用」：差值 ≥ +0.3R 且 bootstrap（10,000 次，种子 20261019，按题重抽）95% 区间下限 > 0。
- 「眼光有害」：差值 ≤ −0.3R 且 95% 区间上限 < 0。其余：「未证明」。
- 035 按日/周/月分格只描述，不单独下结论（每格样本太少）。
- 训练结论只说明 owner 的眼光，不用来改 3W 规则（ADR-16）。

**B. 前向盲判（`research/lab/forward/triangle/judgements.jsonl` 的 user_do / user_no）**
- 用 Task 036 的检查点（已结束 30/60/100 笔）。只描述 do − no 差值与 do 组对随机孪生的结果；≥100 笔且 t ≥ 2.0 才可写「有用」。

**C. owner 自选股前向记录（新）**
- 每笔必须在下一交易日开盘前登记：代码、入场方式（次日开盘市价或限价）、止损、目标、最长持有（默认 26 周）、一句理由。登记后不可修改或删除；撤单另记一行。
- 结果按日线 OHLC 机械计算：同一天同时碰止损和目标按止损算；跳空按开盘价成交；每边成本 0.1%；以 R 记。
- 对照：每笔配 30 只同日随机美股（同样的止损 ATR 倍数和同样的 R 目标），口径与 3W 前向一致；同时并列 3W 前向。
- 判定用 Task 036 同一套：检查点 30/60/100 笔；≥100 笔且对随机 t ≥ 2.0 才写「有效」；30 笔起若均值 < 0 且 t ≤ −2.0 提醒 owner。
- 始终报告笔数、胜率、盈亏比、profit factor、平均 R。

## Step 2 — Eye scorecard (A and B)
`research/lab/eye_judge.py`: inputs are exported answer files (`--daily1 path`, `--mixed1 path`, `--hk1 path`, the private exports already in
`work/v3w/`, e.g. `daily1-overall-10.json`; never read the cloud yourself) and the forward `outcomes.json` + `judgements.jsonl`.
Only revealed cases count; unrevealed or unanswered cases are excluded and counted. Output `work/eye-judge/latest.{json,md}`.
If an export lacks the per-case net R or the choice, stop and report — do not recompute outcomes from prices.

## Step 3 — Own-picks record (C)
- New folder `research/lab/own_picks/` (NOT inside the frozen `research/lab/forward/`): `picks.jsonl` (append-only),
  `outcomes.json` (recomputed). CLI: `python3 -m research.lab.own_picks add SYMBOL --stop X --target Y [--limit Z] [--weeks 26]
  --why "..."` writes `{id, symbol, recorded_at UTC, entry, stop, target, weeks, why}` and refuses a record whose first possible
  session has already opened; `cancel ID`; `compute` (prices from the same sources as `triangle_forward`, read-only import of its
  helpers allowed, no edits to it).
- Tests `tests/test_own_picks.py` on synthetic prices: late record refused; append-only (no edit/delete path); gap through stop;
  stop and target same day → stop; limit never filled; time exit at the week limit; twins use the same ATR multiple and R target;
  checkpoint boundary 29/30; "有效" impossible below 100.

## Deliverables
Ledger §17 entry; `research/lab/eye_judge.py`, `research/lab/own_picks/` + tests; a one-page Chinese how-to for the owner
(`docs/OWN_PICKS_HOWTO_ZH.md`: how to log a pick, what is measured, when a conclusion is allowed). Update `docs/STATUS.md`, add a
`docs/REVIEW_QUEUE.md` row (待核查). Branch `codex/owner-eye`; never merge main. No `.github/` edits: put the suggested weekly
workflow step (compute own picks on Actions) in your report as a patch. Report with Concerns (small samples, the owner seeing
3W signals before picking, selection of which picks get logged).
