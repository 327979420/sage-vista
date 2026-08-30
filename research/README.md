# Sage Vista research ledger

Every factor or model experiment must be recorded before its result is used. The ledger preserves the specification, data window, research version and status, including failed experiments. A favourable result is not a trading recommendation.

Promotion sequence: `idea → challenger → walk-forward validated → paper champion → retired`.

The local SQLite research database is reproducible from `services/scanner/research_pipeline.py` and is intentionally excluded from source control. Versioned aggregate evidence is archived in `research/backtest/output/legacy-foundation/research-report.json`; it is research evidence, not a website asset.

## Minimum acceptable market-data contract

Before a strategy can become a paper champion, its test data must include adjusted daily OHLCV, historical listings and delistings, point-in-time fundamentals keyed to public availability dates, historical classifications, and auditable corporate actions. Missing values stay missing; no future value may be silently carried backward. Every source and transformation receives a version.

Individual factors are tested first. Combination testing starts only after validation-period stability and redundancy analysis: highly correlated indicators count as one family, not multiple confirmations.

## Tracker Backtest V1

当前 Tracker 的独立 point-in-time 历史重放位于 `research/backtest/`。它使用下一交易日 Open、严格长期趋势过滤与 control group、support buffer、固定 R 止盈和完整历史信号账本；输出不进入 production Tracker、评分或 Discord。

## Selection Research V1

`backtest/selection_research_v1.py` 在冻结的 Long benchmark 上独立比较 Leadership 与 Strong-Trend Pullback。所有选股阈值预先固定，特征只读取信号日及之前的数据；结果写入 `backtest/output/selection-research-v1.json`，不会进入 production ranking、Discord 或每日扫描。
