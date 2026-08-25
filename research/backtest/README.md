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
