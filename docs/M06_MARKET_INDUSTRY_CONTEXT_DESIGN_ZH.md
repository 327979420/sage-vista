# M06｜市场与行业上下文设计

- 关联需求：`CR-2026-09-01-046`
- 状态：`implementing`（仅获批影子范围）
- 基线：`f73512584bb412ddced3179a993fabee623a0b7a`

## 人话版

M06像一位只记事的行业顾问。它查清一只股票当时属于哪些ETF，再看这些ETF当时是上涨、回调、接近突破、已突破、走弱还是没证据。它不给股票加分，不排名，也不说买不买。

## 1. 唯一边界

`services/context/`是唯一能创建formal `ContextSnapshot 2.x`身份的中立层。它只接收：

- M02验证后的不可变个股和ETF OHLCV及其行情／股票池身份；
- M03 `GateEvent 2.x`、M04 `TechnicalEvidence 2.x`和M05 `ModelAssessment 2.x`的引用；
- 版本化ETF注册表和带日期成分映射。

M06不调用个股Gate、因子或选股器计算函数。每个ETF在同一`as_of + market_snapshot_id + state_policy_version`下只计算一次，所有成员共享该状态。

## 2. ETF注册表与成分

第一期精选范围为`SPY`、`QQQ`、`IWM`、`XLE`、`SOXX`、`BOTZ`，分别覆盖`broad_market`、`sector`、`industry`和`theme`。这不是“全部ETF”。`BOTT`和`XOXX`未从发行方官方证据确认，不进正式注册表；已核验的相近代码是`BOTZ`和`SOXX`。

注册表保存代码、稳定ETF ID、类型、标签、发行方、官方来源、成分日期、版本、formal当前／未来可用性和历史证据状态。

成分映射是多对多、带`membership_as_of_date`和来源的不可覆盖快照。权重可作客观可选事实，但不参与评分。现有`data/themes/snapshots/2026-08-26-v2.json`来自官方持仓，但仅有ticker/provider code而没有listing生命周期；因此只登记为`legacy/current_membership_bias`，不造formal稳定身份。

## 3. 历史选择

- formal只能选择`effective_from <= as_of`且成员具有M02稳定`instrument_id`的快照。
- 只有更晚快照时返回`unavailable`，绝不拿当前成分倒填。
- 显式legacy可读ticker-only快照，必须附`current_membership_bias`；不得被formal消费。
- 成分新版只追加，相同生效日的不同内容视为冲突。

## 4. ETF技术状态

唯一纯函数使用已完成日K，当前简单政策版本为`m06-etf-state-1.0.0`：

- 长期趋势：收盘不低于EMA200的90%，且EMA200的60日变化不低于-3%；
- 回调：距近期已确认高点5%—25%，并且距EMA21／50／200之一不超过3%；
- 接近突破：未突破且距前60个已完成交易日高点不超过3%；
- 确认突破：当日已完成收盘高于前60日确认高点；
- 结构走弱：收盘低于EMA200的90%，或EMA200的60日变化低于-3%；
- 不足260个已完成日K为`unavailable`。

输出同时保存原始距离、EMA和高点事实，不只保存标签。规则只用于影子客观描述，不是最优参数研究。

## 5. ContextSnapshot 2.x

每只股票生成一份不可变上下文，最少绑定：

- `context_id`、`instrument_id`、`as_of`、`path_status`；
- 个股与ETF的`universe_id`、`market_snapshot_id`和M02复权政策；
- `gate_event_id`、`technical_evidence_batch_id`、`model_assessment_batch_id`及逐条引用；
- ETF注册表版本、成分映射ID、ETF状态ID和客观同向标签；
- `production_effect=false`和明确偏差标签。

formal只接受2.x，1.x仅legacy只读。上下文中禁止`score`、`weight`、`rank`、`trade_plan`、`entry`、`stop`、`target`等字段。

## 6. 个股与ETF的客观连接

一只股票可保留多个ETF上下文，不压成总分。可记录`aligned_uptrend`、`stock_breakout_etf_near_breakout`、`etf_breakout_stock_not_confirmed`、`stock_strong_etf_weak`或`insufficient_evidence`。个股状态只从M03／M04引用提取，M06不重新计算。

## 7. 影子接入与回退

`factor_snapshot`每日影子入口和`unified_v2_scan`回放影子入口只调用同一`services.context.produce_market_industry_context`。默认每日、夜间、网站、Discord、工作流和公开JSON全部不变。失败时停止影子调用即可回退，不需要改生产数据。

## 8. 验收

1. 只有`services/context/`创建formal `context_id`。
2. SOXX—AVGO固定formal样本、BOTZ主题样本和一股多ETF映射通过。
3. 成分日期选择确定；当前快照不能进更早formal回放。
4. 缺历史成分、ETF行情、未完成数据或未知版本失败关闭；legacy不能进formal。
5. 接近突破、确认突破、回调和走弱边界有固定反例。
6. 同一ETF只计算一次，不同输入顺序和`PYTHONHASHSEED`不改身份。
7. 每日与回放对同一输入得到同一身份和内容。
8. M03—M05引用全部对应，没有重算个股Gate、因子或模型事实。
9. 输出不含评分、排名或交易字段，`production_effect=false`。
10. 新成分版本只追加，旧快照内容不变。

## 9. 明确不做

M06不实现评分、排名、交易计划、收益评价、生产接入、网站或Discord。M07—M12各自后续责任本设计不展开。`CR-2026-09-01-043`仍为`captured`。
