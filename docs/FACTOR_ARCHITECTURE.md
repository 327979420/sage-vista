# Sage Vista Factor Architecture

> **历史审计说明**：本文主体冻结在 2026-08-26 的 27 因子迁移审计，用于保留当时事实。当前因子库已为 37 项；当前业务、周期权重和实验纪律以 [`SAGE_VISTA_RULEBOOK_ZH.md`](SAGE_VISTA_RULEBOOK_ZH.md) 与生成的 `public/factor-registry.json` 为准。后续不得根据本文旧数量回退当前实现。

最后审计：2026-08-26。Core migration 状态：27 个注册 ID 全部进入 deterministic daily snapshot；25 个有 objective canonical detector，2 个明确为 `definition_required`。本文是因子系统现实、边界与迁移规则的权威说明；已完成实验及结论仍以 `research/EXPERIMENTS.md` 为准。

> **MONITOR BROADLY, SCORE CONSERVATIVELY.** 监控表示系统保存可复核的技术状态，不表示因子有效、已验证或应进入正式分。

## 1. 结论与术语

仓库中的“factor”不是一种对象，而是四类证据：

1. **Setup / Event**：金叉、修复、突破、回踩、K 线和支撑命中；回答“此刻是否发生事件”。
2. **Continuous Ranking**：动量、相对强度、波动率、流动性、ADX 等连续值；主要用于横截面研究。
3. **Qualification / Risk**：长期趋势、回调位置、上方供给等门槛或风险，不应被误当作独立 alpha。
4. **Context**：Market ETF Context 与 Industry Radar；只供人工决策，绝不并入 Technical Tracker 排名。

27 个注册项是研究目录，不是 27 个生产评分项。初次审计时只有 23 项可找到相同或近似实现，且 Rare 只条件计算少数组件。迁移后 snapshot 对每个 eligible ticker 持久化全部 27 个 ID：25 项为 monitored hit/non-hit，2 项以 unavailable/definition-required 持久化；正式分仍为 0。

### Active monitoring 的产品定义

只有同时满足以下条件才可标记 `actively_monitored=true`：

- 有 canonical detector；
- 在对应频率对每个 eligible ticker 计算；
- 结果写入可按 `as_of` 重现的每日输出，包括未命中；
- 命中无需重跑研究即可在 UI/context 出现；
- 只使用 `as_of` 及之前的完整 bar。

主动监控与计分无关。Candidate 可以每日监控但 official score 为零。

## 2. 三条相互独立的状态轴

现有 `status` 主要表达研究状态，不能继续兼任运行状态。

- **research_status**：`pending → testing → candidate → validated`；旁路终态为 `rejected / unstable / insufficient_sample / paused`。
- **runtime_status**：`not_implemented / implemented / scheduled / monitored / paused`。
- **score_role**：`none / display_only / observational / official`。只有 `validated` 可为 `official`；rejected、unstable、pending、testing、insufficient、paused 必须为零权重。

建议生命周期是 `REGISTERED → IMPLEMENTED → SCHEDULED → MONITORED`，研究生命周期独立推进。Promotion 只改变 research status / score role，不能由“代码存在”自动触发。

## 3. 27 项注册因子清单

缩写：`C`=只在 Rare 候选通过前置过滤后条件计算；`T`=Tracker 每日路径；`R`=研究/回测路径；`UI-reg`=因子库元数据可见；`UI-hit`=命中高分后可见。所有项目当前严格 Active 均为“否”。“安全”表示代码按 point-in-time 窗口或完整周期执行；“关注”表示 pivot 定义、定义漂移或版本重放仍需补证。

| canonical_id | 名称 / family | 实际实现与每日路径 | 展示 / ranking | 研究 / leakage | duplicate / dependency | action |
|---|---|---|---|---|---|---|
| `qualification.long_trend` | 长期趋势资格 / qualification | `long_trend_ok`；C | UI-reg/核心说明；none | candidate；安全 | Tracker EMA 同族、非重复 | KEEP, MONITOR |
| `qualification.pullback_60d` | 60 日高点回调 / qualification | `daily_pattern_flags`；C | UI-reg/核心说明；none | candidate；安全 | 无 | RESEARCH |
| `macd.daily_bull_cross` | 近 5 日金叉 / MACD | `recent_bull_cross`；Rare 前置 | UI-hit；observational | candidate；安全 | Tracker fresh-cross 同族不同产品窗口 | KEEP, MONITOR |
| `macd.weekly_histogram_improving` | 完整周柱改善 / MACD | `macd_state`；C | UI-hit；observational | candidate；完整周安全 | Tracker weekly layer 同源证据 | KEEP, MONITOR |
| `macd.monthly_bull_cross` | 完整月线金叉 / MACD | Tracker completed-month；T | Tracker/UI-reg；Tracker separate ranking | candidate；完整月安全 | Tracker MACD layer | KEEP |
| `support.ema_proximity` | EMA21/50/200 支撑 / support | `daily_pattern_flags`；C | UI-hit；observational | candidate；安全 | Tracker EMA layer 是方向/触发，非重复 | KEEP, MONITOR |
| `support.fibonacci_half` | Fib 0.5 / support | `fibonacci_support_levels`；C | UI-reg；display only | rejected；pivot 确认需专项复核 | 与 0.618 同组 | REJECT |
| `support.fibonacci_618` | Fib 0.618 / support | canonical swing detector；daily snapshot | UI-reg/snapshot；auxiliary experimental 1 | candidate；关注 | 依赖已确认 swing；同组 cap | MONITOR, RESEARCH |
| `support.golden_pocket` | Golden Pocket / support | objective 0.5–0.618 zone；daily snapshot | UI-reg/snapshot；display only | pending；关注 | Fib 同组 cap | MONITOR |
| `structure.trendline_three_push` | 三推突破 / structure | `three_push_breakout_setup`；C/R | UI-reg；display only | unstable；point-in-time 窗口，pivot 语义待复核 | retest 父项 | REJECT/历史保留 |
| `structure.double_bottom` | 双底 / structure | `detect_w_bottom`；C/R | UI-reg；none | rejected；2-bar 规则需保持 | higher-low 同组非同信号 | REJECT |
| `structure.higher_low` | 更高低点 / structure | confirmed canonical pivots；daily snapshot | Tracker/UI-reg/snapshot；display only | pending；定义一致性关注 | Tracker 近似实现 | MONITOR, MERGE definition |
| `structure.breakout_retest` | 通用突破回踩 / structure | definition_required | UI-reg/snapshot unavailable；none | none；规则不足 | 未指定 structure/level/invalidation | HOLD |
| `structure.trendline_three_push_retest` | 三推回踩 / structure | `three_push_retest`；C | UI-hit；observational | candidate；point-in-time，pivot 待复核 | depends on 三推突破 | MONITOR, RESEARCH |
| `structure.bullish_fvg_support` | Bullish FVG / structure | gap window detector；C | UI-hit；observational | candidate；安全 | 无 | MONITOR, RESEARCH |
| `risk.overhead_unfilled_gap` | 上方未补缺口 / risk | gap window detector；C | UI-hit；observational | candidate；安全，但“风险加正分”语义需研究 | 无 | RESEARCH |
| `rsi.oversold_repair` | RSI 超卖修复 / RSI | canonical RSI30 exit；daily snapshot + memory | Tracker/UI-reg/snapshot；display only | pending；安全 | raw `rsi_14` 不是重复 | MONITOR |
| `rsi.bullish_divergence` | RSI 底背离 / RSI | confirmed-pivot canonical detector；daily snapshot + memory | Tracker/UI-reg/snapshot；display only | unstable；零分 | Tracker 实现仍独立 | MONITOR, REJECT score |
| `volume.relative_expansion` | 相对放量 / volume | prior-20 ratio >= registered strong 1.5；daily snapshot + memory | Tracker/UI-reg/snapshot；display only | testing；安全 | research `volume_expansion` 同一 raw ratio | MONITOR, MERGE primitive |
| `volume.bottom_expansion` | 支撑位底部放量 / volume | `daily_pattern_flags`；C | UI-hit；observational | candidate；安全 | 运行时依赖 support context，元数据尚不能表达 OR dependency | MONITOR, RESEARCH |
| `volume.pullback_contraction` | 缩量回调 / volume | definition_required | UI-reg/snapshot unavailable；none | none；缺 pullback/baseline/threshold | continuous contraction 同族 | HOLD |
| `structure.bottom_doji` | 底部 Doji / structure | candle detector；C/R | UI-reg；none | rejected；安全 | bottom-candle 同组 | REJECT |
| `structure.bottom_bullish_engulfing` | 底部吞没 / structure | candle detector；C/R | UI-reg；none | rejected；安全 | support engulf 共用 candle primitive、位置不同 | REJECT |
| `structure.support_bullish_engulfing` | 支撑位吞没 / structure | `daily_pattern_flags`；C | UI-hit；observational | candidate；安全 | 运行时依赖 support context | MONITOR, RESEARCH |
| `structure.hammer` | 锤头 / structure | registered wick/body config；daily snapshot + 3-session memory | UI-reg/snapshot；display only | pending；安全 | bottom-candle 同组 | MONITOR |
| `support.close_congestion` | K 线聚集 / support | `congestion_support`；C/R | UI-reg；none | rejected；安全 | volume profile 同组但算法不同 | REJECT |
| `support.volume_profile_proxy` | 成交量分箱筹码峰 / support | `volume_profile_support`；C/R | UI-reg；none | rejected；安全；只是日线近似 | congestion 同组 | REJECT |

审计基线汇总：27 registered；23 implemented/近似 implemented；23 会在某条 scheduled path 中计算但多为条件计算；迁移前 0 严格 actively monitored；8 当前可进入 Rare observational score；0 official registry score；8 rejected/unstable。迁移代码已把初始 8 项接入全 eligible-universe snapshot；在下一次真实 daily output 成功落盘前，其 operational 状态仍标记为“configured，awaiting first production snapshot”。

## 4. 注册表外的 factor-like concepts

### Technical Tracker（产品专用机会引擎）

| canonical_id | machine definition | daily / displayed | ranking | relationship / action |
|---|---|---|---|---|
| `tracker.macd.multitimeframe` | completed daily/weekly/monthly MACD direction, trigger and custom layer score | T / yes | separate tracker ranking | 复用 canonical MACD primitives，保持排名契约 |
| `tracker.rsi.reversal` | multi-timeframe RSI direction/repair/divergence layer | T / yes | separate tracker ranking | raw RSI 与事件分层，不塞入 Registry score |
| `tracker.ema.direction_trigger` | EMA20/50 direction, cross and improving state | T / yes | separate tracker ranking | 与 EMA proximity 不同 |
| `tracker.breakout.prior20_close` | close breaks prior 20 completed-session high/low | T / yes | separate tracker ranking | 与 252 日 breakout 不同 horizon |
| `tracker.volume.near_bottom` | volume/prior-20 average，60 日底部位置与涨跌方向 | T / yes | 辅助 Tracker | 与 relative expansion 共用 primitive |
| `tracker.price_structure` | trend/support/higher-low/breakout evidence aggregation | T / yes | 辅助/qualification | 拆出 canonical primitives 前保持现状 |
| `tracker.early_watch` | 多层接近触发及结构确认组合 | T / yes | Tracker product state | 不是独立 alpha factor |

推荐 **Option B**：Tracker 保持独立产品与原排名；以后只逐步消费经过 parity test 的 canonical primitives。Registry 不拥有 Tracker 的产品权重。

### Research Pipeline（13 个连续横截面特征）

`research_pipeline.factor_values` 计算：

| canonical_id | machine definition（截至 as_of） | relationship / action |
|---|---|---|
| `research.momentum_12_1` | 252 日至 21 日前收益 | continuous ranking；KEEP research |
| `research.momentum_6_1` | 126 日至 21 日前收益 | 同上 |
| `research.momentum_3_1` | 63 日至 5 日前收益 | 同上 |
| `research.trend_quality` | close/EMA200 与 EMA50/EMA200 的连续组合 | long-trend 同族，非重复 |
| `research.low_volatility` | 长窗 realized volatility 的负值 | continuous ranking |
| `research.liquidity` | dollar ADV 的 log | ranking/qualification 可共享 raw primitive |
| `research.rsi_14` | RSI14 连续值 | RSI event 的输入，不是 event |
| `research.macd_strength` | (MACD-signal)/ATR | MACD cross 的连续强度，不是 cross |
| `research.adx_14` | ADX14 | continuous ranking |
| `research.volume_expansion` | current volume/prior mean | 与 registry relative expansion 共用 raw primitive |
| `research.breakout_252` | close/prior-252 high - 1 | Tracker 20 日 breakout 不同 horizon |
| `research.volatility_contraction` | -short_vol/long_vol | pullback contraction 同族不同定义 |
| `research.relative_strength_6m` | stock 6m return - benchmark 6m return | stock selection；不是 Industry theme leadership |

这 13 项是 research-only continuous features，不应自动进入 event registry 或 Rare score。研究 forward return 只作 outcome，不作 selection input。

### 重复审计

发现 8 个 overlap clusters：MACD、RSI raw/事件、RSI divergence 双实现、relative volume、breakout、trend/EMA、relative strength、candle/support primitives。它们大多是同族不同用途；当前 **0 个可以不经定义一致性测试就直接合并的完全重复信号**。应 MERGE 的是 primitive 与 identity，不是产品分数。

## 5. 生命周期断点与 Registry truthfulness（审计基线与修复）

- Registry → Detector：Golden Pocket 与 hammer 已补 objective detector；generic breakout-retest 和 pullback contraction 因定义不足保留 `definition_required`。0.5、0.618、Golden Pocket 现在各有独立 identity，但受同一 redundancy cap。
- Detector → Daily：已由全 eligible-universe snapshot 修复；Rare 只消费 snapshot，不再决定哪些 detector 运行。
- Daily → Output：已持久化 27 个 ID 的 hit/non-hit、availability、event memory 和 versions。
- Output → UI：UI 可展示全部 registry metadata，容易让“已登记”看起来像“已监控”。
- Research → Registry：research refs 是人工字符串，没有验证引用存在或自动同步状态。
- Version → Replay：历史 signal 没有携带完整 detector definition snapshot；今天的 registry 可能改变历史解释。
- 原运行时未读取 `score_mode/weight/status`，rejected Fibonacci 0.5 与 unstable 三推仍各按一分；dependency/redundancy 也未在计分时执行。本次已修复并加入 contract test。
- support-context OR dependency 现由 registry `dependency_policy=support_context` 与 evidence 共同执行；普通 `depends_on` 继续表示全部父项必须成立。
- `public/factor-registry.json` 是 Python registry 的生成物，改 metadata 后必须重建并测试一致性。

## 6. 系统模块地图

| 模块 | Purpose / Input | Output / 更新 | Registry / ranking | overlap risk / recommendation |
|---|---|---|---|---|
| Technical Tracker | EOD bars → 四层股票机会与状态 | tracker JSON；daily EOD | 不消费；影响独立排名 | 中；保持排名，渐进共享 primitives |
| Rare Opportunity Radar | 候选 EOD bars → setup evidence | rare JSON；daily EOD | 部分 ID mapping；observational | 高；改为消费 daily snapshot |
| Factor Registry | 身份、规则、研究/计分 metadata | Python + public JSON；定义变更时 | source of metadata；不计算 | 状态过载；拆三轴 |
| Factor Research | point-in-time bars/universe → 横截面统计 | research artifacts；实验时 | 不消费 event registry | 同名误解；保留 continuous taxonomy |
| Market ETF Context | ETF ratios/regime | context JSON；daily | 不影响 stock ranking | 低；保持 context |
| Industry Radar | dated membership + prices → theme state | industry-radar JSON；独立运行 | 不消费；不影响 Tracker | 不得变成 stock alpha |
| Backtest / Experiment Registry | historical bars → outcome | artifacts + `EXPERIMENTS.md` | research authority | 保留失败和样本不足，不回写历史 |
| Daily updater/workflow | EODHD/cache → 各产品 artifacts | daily EOD | orchestration only | 不应内嵌第二套 detector |
| Discord | 已发布同源 JSON → 通知 | webhook；成功发布后 | 不重新计分 | 必须保持同源、fail closed |

## 7. Future leakage 审计规则与结果

- rolling window 必须截断在 `as_of`；当前 Tracker、Rare 与 Research 的主要 rolling 计算符合。
- weekly/monthly 必须只用 completed groups；Tracker 与 MACD backtest 当前符合。
- forward 20/100 日收益只可作 outcome；当前 research/backtest 选择逻辑未使用 outcome。
- swing/pivot 必须等待确认延迟后才可见。双底/RSI divergence metadata 写了 2 bars，但三推与 Fibonacci 的 swing helper 及 Tracker divergence 有不同定义；结论为 **concern，未发现已证实的 future leakage**，在统一前不能仅凭 `lookahead_safe=true` 宣告验证。
- 每个 daily snapshot 必须记录 `registry_version`、每个 `factor_version` 和 `as_of`，否则定义更新会产生语义型历史泄漏。

## 8. Promotion review（不自动 promotion）

- **Group 1 — Keep / monitor now**：daily MACD cross、completed-week histogram、EMA proximity、三推 retest、Bullish FVG、overhead gap、support bottom volume、support bullish engulfing。均保持 observational；overhead risk 的正分语义需显著标识。
- **Group 2 — Research next**：0.618 独立身份、三推 retest、FVG、overhead gap、两项 support confirmation；同时做 Tracker/Research primitive parity。
- **Group 3 — Hold**：Golden Pocket、generic breakout-retest、pullback contraction、hammer，以及未独立验证的 60d pullback。
- **Group 4 — Rejected / unstable**：Fib 0.5、三推 breakout、double bottom、RSI divergence、bottom Doji、bottom engulfing、congestion、volume-profile proxy。保留历史，零分。
- **Group 5 — Merge / rename**：RSI divergence 双实现、relative-volume primitive、MACD/EMA/RSI raw primitives；先 parity test，绝不合并产品 ranking。

## 9. 最小迁移规格

不建设数据库，也不建设巨型 `factor_engine.py`：

1. 给 registry 增加独立 `research_status`、`runtime_status`、`score_role`、`detector_ref`；保留兼容字段直到 consumer 迁完。
2. 将 indicator、rolling window、confirmed pivot 等放在小型 shared primitives；每个 canonical detector 返回稳定结果对象。
3. 由 daily updater 对每个 eligible ticker 生成紧凑 `daily-factor-snapshot.json`：`ticker, factor_id, as_of, factor_version, value, hit, evidence, runtime_status, research_status, score_role`，并包含未命中。
4. Rare 先消费 snapshot；并行比较旧/新输出后切换。Tracker 只在 primitive parity test 通过后逐项消费，排名公式不变。
5. Research adapter 尽可能调用同一数学定义，但连续 rank feature 与 event detector 保持不同 canonical ID。
6. 加 factor #28 的顺序：写机器定义与依赖 → 注册 ID/version → 实现 point-in-time detector → unit/leakage test → 全 universe snapshot shadow monitoring → 注册实验 → 人工 promotion。禁止直接把名字加入 UI 或 score list。

## 10. Core migration contracts

### Shared primitives audit

| Primitive | 当前实现 | 决定 |
|---|---|---|
| EMA / MACD / RSI / ATR | `technical.py` 为主；部分旧研究 wrapper | canonical detectors 复用现有实现；不为整洁而重写 Tracker |
| rolling high/low / prior-volume average | 各 detector 的明确 point-in-time slice | 保留局部规则，未来只在数学完全相同时抽取 |
| confirmed pivots | `detectors.pivots`，按 configured right bars 确认 | 复用并测试 confirmation delay |
| completed weekly/monthly | Tracker `aggregate` 与 research `completed_groups/available` 输入格式不同 | 初始 detector 复用 research legacy 路径以保证 Rare parity；不盲目合并 |
| as_of trimming | 新 canonical boundary `trim_as_of` | 所有 detector 调用前统一截断；future mutation test 覆盖 |

### Canonical detector contract

`factor_detectors.evaluate_all_factors(rows, as_of)` 返回 registry 稳定顺序的：

```text
factor_id, factor_version, as_of, value, hit, recent_hit,
latest_hit_date, bars_since_hit, evidence, available, runtime_status,
factor_type, research_status, score_role, experimental_weight,
lookahead_audit
```

Detector 不读取 status/weight，不做 scoring，也不决定 Rare threshold。`available=false` 与 `hit=false` 不得混为一谈。

### Daily snapshot contract

`python3 -m services.scanner.factor_snapshot --as-of YYYY-MM-DD` 生成 `public/daily-factor-snapshot.json`。顶层包含 `as_of`、`registry_version`、`mode=shadow_monitoring`、`future_data_used=false`、27 个固定 `factor_ids`、`eligible_count` 和按 symbol 排序的 records；每个 eligible symbol 必须恰好包含 27 条状态，包括 25 条可用状态和 2 条 `definition_required`。输出不含 wall-clock timestamp，因此相同输入 byte-deterministic；持久化使用稳定 key order 的紧凑 JSON，以满足 Cloudflare Workers 25 MiB 单资源限制，不改变数据 contract。

Daily updater 以临时目录依次生成 Tracker、snapshot、Rare，完成日期、27-ID completeness 与 leakage validation 后才原子发布。Snapshot 不进入 Tracker ranking 或 Discord；Rare UI 只展示已进入 Rare signal 的当前/近期 canonical evidence。

### Event-memory model

Event window 是 registry metadata，不散落在 UI：MACD 5 sessions；三推/双底/retest/RSI divergence 10；RSI repair、relative volume、bottom/support engulfing、bottom volume 5；Doji/Hammer 3。State/qualification/risk 因子只表达当前状态，不伪造 event age。

- `hit`：在 as_of 当前成立。
- `recent_hit`：event 在注册 observation window 内发生。
- `latest_hit_date`：最近一次客观 event date。
- `bars_since_hit`：从该 event 到 as_of 的已完成 session 数。

Daily MACD 的 `hit` 保留原有“近 5 session 金叉且仍为多头”语义，但 memory 会定位真实 cross date，不把每天误写成新金叉。

### Experimental scoring policy

- **Core observational**：原 8 项，每项 provisional weight 2。
- **Auxiliary observational**：long-trend、60d pullback、completed-month MACD cross、Fib 0.618，每项 provisional weight 1。
- **Display only**：其余 15 项 weight 0；包括 rejected、unstable、testing/pending 未批准计分项和 ambiguous 项。
- `official_score` 当前恒为 0。`experimental_observational_score` 只是产品 shadow heuristic，不是 confidence、probability、win rate 或 alpha。
- 为保持已有 Rare/Discord 门槛兼容，现有 `total_score/observational_score` 不改名、不改 threshold；新实验分作为独立字段，不触发新 Discord 行为。
- 每个 `redundancy_group` 只取最大 contribution；同权时按稳定 factor ID 决定，避免 Fibonacci/RSI/structure 重复堆分。
- `depends_on` 和 `dependency_policy` 在 score consumer 中强制执行。Support bottom volume 与 support engulfing 必须保存并满足当时的 `support_context=true`。

### Parity and versioning

- 52 个历史 as_of、416 个 legacy/canonical state comparisons：100% agreement，0 mismatch（synthetic deterministic fixture，包含不同周界）。
- Registry 的 weekly histogram 文本原先只描述一次比较，legacy 实际要求连续两次非下降；已修正 metadata，factor version 为 `1.0.1`，数学行为未改变。
- Rare 现在从 snapshot 读取 8 项数学状态，再应用原有 core qualification、registry score role/weight、dependency、redundancy 和 threshold。
- 每个 persisted state 固定 `registry_version + factor_id + factor_version`。未来数学定义改变必须升 factor version；旧实验和旧 snapshot 不改写。

### Research impact / revalidation specification

旧结果继续准确描述旧 frozen specification；“needs rerun”表示若要声称它代表**当前**零 rejected/unstable 分的 contract，必须创建新 experiment ID/version，不能覆盖旧文件。

| Experiment | Affected | Needs rerun | Reason |
|---|---:|---:|---|
| MACD Multi-Factor Score V1 | YES | YES | 六项旧等权含后来 rejected Fib 0.5 与 unstable 三推；需 V2 current-contract replay |
| Tracker Backtest V1 score/Confirmed diagnostics | YES（局部） | YES（只重跑 current-score comparison） | historical replay 调用了旧 multi-factor score；Tracker layer ranking 本身未变 |
| Stop Loss / Risk-Reward V2 | NO | NO | 固定 V1 signals 后只比较 exits；原结论仍属于 frozen sample |
| Market Regime V1 | NO | NO | 固定 benchmark 与 context 分组，不依赖当前 Rare score |
| Factor Attribution V1 | YES | YES | score buckets、factor states 与预定义 pair 使用旧 replay ledger |
| Ranking Research V1 | YES（B/C） | YES | Multi-Factor 与 Hybrid rankers 使用旧 score；MACD/Random/No-Rank 可保留 |
| Selection Research V1 | NO | NO | 固定 benchmark 的独立 leadership/pullback selection，不以 Rare score 选样 |
| Research Pipeline v0.3 continuous factors | NO | NO | 不消费 event registry 或 Rare score |

Rerun 顺序：冻结原 universe/entry/outcome → 用 versioned canonical state 重建 current score → 新建 `macd-multifactor-score-v2` → 依次产生 Tracker score diagnostic V2、Factor Attribution V2、Ranking Research V2。不得把本次 unit parity 当成新的 alpha 实验，故不更新 `research/EXPERIMENTS.md`。

### 27-factor monitoring status

- **Monitored / available（25）**：所有注册项，除下述 2 项。Rejected/unstable 仍计算并展示，但零分。
- **Definition required（2）**：`structure.breakout_retest` 没有指定被突破结构、level 与 invalidation；`volume.pullback_contraction` 没有定义 pullback、baseline 与 contraction threshold。两者每天持久化 `available=false`，禁止猜规则。
- **Recent-event memory（12）**：daily MACD、three-push breakout/retest、double bottom、RSI repair/divergence、relative volume、bottom volume、Doji、bottom engulfing、support engulfing、hammer。
- **Continuous/state/qualification/risk（13 available + 2 unavailable）**：只报告当前状态，不套 arbitrary recent window。

## 11. 已知限制与迁移状态

- `daily-factor-snapshot.json` 已进入 production daily contract：与 Tracker、Rare Radar 和 update status 在临时目录完成同日、完整 registry、版本及防前视验证后一起发布，并由 daily workflow 提交。它仍是 shadow monitoring，不进入 Technical Tracker ranking 或 Discord threshold。
- 真实全 universe snapshot 必须在持有 EODHD Repository Secret 的 GitHub Actions 中生成；本地没有 token/cache 时不得把无数据误报为未检测。
- Rare 兼容门槛仍只使用原有 score contract；27-factor experimental score 尚未经过历史验证。
- candidate 不代表验证有效；Registry official score 当前为 0。
- 下一预注册研究比较 Core-only、Core+Auxiliary、No observational ranking，使用 20D/100D outcome、PF、expectancy、drawdown、ranking monotonicity 与 sample stability，并保持 development/validation/forward split；不得用 forward outcome 调窗口或权重。
- `research/EXPERIMENTS.md` 是完成实验的唯一 authoritative registry；本文不创造实验结论。
- Technical Tracker、production strategy、Discord 与 Industry Radar thresholds 是禁止在因子迁移中顺手修改的生产边界。

### Production freshness and deployment verification

- `.github/workflows/eod-freshness-monitor.yml` 是独立于 daily EOD workflow 的迟到检查入口。它重新向 EODHD 查询最新完整交易日，再比较 repository status 中的 source、Tracker、factor snapshot、Radar 四个日期；stale 时上传证据、创建按 provider date 去重的 GitHub issue 并使检查失败。`repository_dispatch: eod-freshness-check` 保留给外部调度器，避免未来只能依赖 GitHub cron。
- Live verification 每一轮都重新获取`update-status.json`、`favorite-pattern.json`、`daily-factor-snapshot.json`、`rare-opportunity-radar.json`和最新紧凑排行／账本，并重新执行完整跨文件日期、共享MACD门票与防前视检查。静态资源短暂出现mixed-date propagation时继续重试；只有整组文件一致才允许Discord，重试耗尽则失败关闭。
- Freshness monitor 不负责修改数据，live verifier 不改变 EODHD market-date detection；两者只做独立检测和发布后审计。

## 12. Industry Radar 的独立下一步

按既定计划：完成约 20 个 source-ready Themes；实现 iShares、First Trust、State Street、Invesco、VanEck adapters 并保留 Global X；同一 effective date 生成 immutable candidate snapshot；计算 US-tradeable counts 与 pairwise overlap；标 near-duplicates；用 EODHD 跑一次真实 snapshot 后再决定 V1。AI Infrastructure、Semiconductor Equipment、Data Center Power 在证据规则批准前继续为 `manual_curated_required`，不得猜 membership。
