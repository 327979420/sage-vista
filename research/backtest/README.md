# Tracker Backtest V1

这是与 production Tracker、雷达和 Discord 完全隔离的研究回测。

## 固定设计

- Long only；逐历史交易日重放当前 Long Early Watch／Confirmed 选择面并保留当日 Top 10。
- 信号只使用当日及以前的完整日线、上一根完整周线和上一根完整月线。
- 信号在完整收盘后形成，下一交易日复权 Open 入场。
- 严格长期趋势过滤：`Close > EMA200` 且 `EMA200 > 20个交易日前EMA200`；同时保留 control。
- support 只从信号时可见的 EMA21/50/200、最近20日低点和已确认 swing low 中选择。
- 固定测试 support 下方 1%、2%、3%、5%；不根据结果自动选择。
- 同一日线同时触及 stop 和 target 时保守按 stop first。
- Forward return：1/3/5/10/20/40日；MFE/MAE：40日；额外测试1R/2R/3R。

## 输出

- `output/summary.json`：页面和结论使用的汇总。
- `output/signals.jsonl`：完整历史信号账本，包含 Ticker、日期、排名、因子状态、分数、状态、support、下一日开盘和结果路径。

运行：`python3 -m research.backtest.tracker_backtest_v1 --start 2010-01-01`。

V1 使用378只确定性 survivorship-aware 研究样本，其中包含111只退市股票，但仍不是完整历史美股 universe。所有结果只属于 Research/Strategy 层，不得进入 production 权重、排行榜或 Discord。

## Tracker Backtest V2

V2 直接读取冻结的 V1 信号账本，只研究 Stop Loss / Risk-Reward，不重新扫描，也不改变生产 Tracker、因子、Ranking、Entry、Discord 或网站生产数据。运行 `python3 -m research.backtest.tracker_backtest_v2`，汇总输出为 `output/v2-summary.json`。

## Market Regime V1

Market Regime V1 仅把固定、未调参的 SPY/QQQ 趋势、MACD 动能和历史 breadth 作为研究变量，附加到冻结的 `Confirmed + strict trend + next Open + Support −5% + 2R` benchmark。它不自动过滤 production 信号或改变仓位。运行 `python3 -m research.backtest.market_regime_v1`，输出为 `output/market-regime-v1.json`。

## Factor Attribution V1

Factor Attribution V1 在同一个冻结 benchmark 上逐项比较“有因子”和“无因子”，并分开发期、2025验证期与2026前向期诊断。仅检查三组预定义语义组合，不进行自动组合搜索，不改 production 权重或 Ranking。运行 `python3 -m research.backtest.factor_attribution_v1`，输出为 `output/factor-attribution-v1.json`。

Score / Factor Study V1 复用冻结事件池，按预登记口径检查评分单调性、单因子基础出现率与富集、开发期冻结的跨家族两因子组合，并保存自然周检查点。运行 `python3 -m research.backtest.score_factor_study_v1`，输出 `output/score-factor-study-v1.json` 和 `output/score-factor-study-v1-weekly.jsonl`。

## Context Comparison V1

Context Comparison V1 固定比较四组：旧技术基准、技术+行业、技术+大盘、技术+行业+大盘。所有组共享同一批技术信号和入场定义，不搜索最佳权重；行业成员关系和上下文必须在信号日已有带日期快照，否则记为 unavailable，不允许用今天的成员表回填历史。统一输出 5/20/60/100 日胜率、均值/中位数收益、相对 SPY、MFE、MAE、最大回撤和年度稳定性。历史回测与 production-forward 分开报告。

Winner / Loser Strategy Optimization V1 复用完整V2事件产物与Actions价格缓存，保存开发期最大100赢家／输家，增加冻结的连续技术特征，并只用2001—2018发现、2019—2024内部校准形成家族去重整数权重。2025与2026只验收、不调参；详细100名单保存在压缩Actions产物，仓库只保存紧凑挑战者与三时期结论。运行入口为 `python3 -m research.backtest.winner_loser_optimization_v1`，工作流为 `winner-loser-strategy-optimization.yml`。

## Ranking Research V1

Ranking Research V1 重放完整 point-in-time 固定 benchmark 候选池，比较 MACD、Multi-Factor、固定50/50 percentile Hybrid、固定 seed Random 与 No Ranking。候选账本和汇总分别保存在 `output/ranking-research-v1-candidates.jsonl` 与 `output/ranking-research-v1.json`。不调参、不改 production Ranking。
