# M04｜统一因子事实与 TechnicalEvidence 设计包

- 关联需求：`CR-2026-09-01-044`
- 状态：`verified`（本地实现与验收完成，尚未提交、合并或生产启用）
- 基线：`547949bad8c3447aeeb7665723ed49178f8050f2`
- 边界：本文件只设计，不授权实施、提交、合并、部署或生产切换。

## 人话版

现在同一个因子可能在日终快照、回放扫描或辅助入口里被重复计算；结果又藏在不同JSON和字典里。M04要做的事情很简单：每只股票、每个信号日的客观因子只算一次，由一个中立入口开出一叠有编号、有来源的“因子验货单”。

这叠验货单就是`TechnicalEvidence`。它只回答“当时哪些事实存在、证据是什么、是否可用”，不回答“得几分、排第几、买不买、怎么持有”。

## 1. 当前真实链路与重复点

| 当前位置 | 当前职责 | M04判断 |
|---|---|---|
| `services/scanner/factor_registry.py` | 39项历史快照对应的因子ID、版本、周期、家族和父条件 | 保留为唯一因子说明书；数量必须动态读取，不能把39写成永久常量 |
| `services/scanner/factor_detectors.py::evaluate_all_factors` | 在点时K线上计算全部因子状态 | 作为现有计算事实来源迁入唯一生产层，不复制公式 |
| `evaluate_initial_factors` | 先计算全部因子再筛初始集合 | 容易在同一流程重复全量计算；M04只允许一次计算后派生视图 |
| `services/scanner/factor_snapshot.py::build_snapshot` | 重做价格、历史、流动性和MACD检查，同时混入因子、实验分和支撑计划 | 生产兼容期保持原样；M04不得把门卫、评分或交易计划带入新证据合同 |
| `services/scanner/unified_v2_scan.py` | 每日／回放重新构建旧快照并继续评分、排行 | M04只提供影子证据入口；不修改现有评分或默认结果 |
| `services/contracts/validation.py` | 仅有较薄的`TechnicalEvidence 1.x`校验 | 新formal语义使用新主版本；1.x仅legacy只读 |

当前主要问题不是因子公式一定错误，而是没有独立、不可变、可复用的事实层。消费者可以从嵌套字典猜字段，也无法机械证明每日与回放使用的是同一份证据。

## 2. M04唯一职责

> M04接收M02不可变点时行情与M03唯一GateEvent，把注册表内的客观因子事实计算一次并生成不可变TechnicalEvidence；止于事实，不进入评分。

目标链路：

```text
M02不可变行情 + M03 GateEvent + 因子注册表
→ services/factors/唯一生产者
→ TechnicalEvidence 2.x集合
→ M05以后只读消费
```

只有`services/factors/`可以创建新的`evidence_id`。扫描器、回放、个人形态、网站和研究脚本不得复制合同或另建事实生产器。

## 3. 输入边界

formal生产必须同时收到：

- `GateEvent 2.x`及其`gate_event_id`、`instrument_id`、`signal_date`、`path_status`；
- M02验证并冻结的调整后OHLCV、`market_snapshot_id`、`universe_id`、`as_of`和完整`ADJUSTMENT_POLICY`；
- 因子注册表版本及当次有效因子定义；
- 明确的因子检测政策版本。

所有身份、日期和formal路径必须互相一致。formal股票池、GateEvent或行情证据缺失时失败关闭，不得自动退回legacy。legacy只能由调用者显式选择，并原样传播偏差标签。

M03已经拥有的精确MACD和既有长期资格事实，不在M04重新计算。注册表中对应因子由M04生成“引用型证据”，绑定原GateEvent字段及身份；其他因子才调用唯一检测器计算。

## 4. 输出合同

推荐新增`TechnicalEvidence 2.0.0`，每个有效注册因子恰好生成一条证据。最小字段：

```json
{
  "schema_version": "2.0.0",
  "evidence_id": "evidence:sha256:...",
  "gate_event_id": "gate:sha256:...",
  "instrument_id": "instrument:sha256:...",
  "as_of": "YYYY-MM-DD",
  "path_status": "formal",
  "universe_id": "universe:sha256:...",
  "market_snapshot_id": "market:sha256:...",
  "adjustment_policy": {"version": "...", "formula": "..."},
  "registry_version": "...",
  "detector_policy_version": "...",
  "factor_id": "...",
  "factor_version": "...",
  "family": "...",
  "timeframe": "daily|weekly|monthly|cross_period",
  "source_kind": "gate_reference|factor_detector",
  "available": true,
  "raw_hit": false,
  "qualified_hit": false,
  "blocked_by": [],
  "recent_hit": false,
  "latest_hit_date": null,
  "bars_since_hit": null,
  "value": null,
  "evidence": {},
  "future_data_used": false
}
```

规则：

- `raw_hit`只保存检测器看到的客观形态；`qualified_hit`还必须满足注册表父条件；父条件缺失或不可用时不得把子因子算作命中，原因写入`blocked_by`。
- `available=false`不等于零分；必须说明缺失原因。
- `evidence`保存结构化事实，不保存分数、权重、排名、交易建议或收益评价。
- 周线、月线只使用完整收盘周期；pivot必须等待右侧确认；`as_of`之后的数据不得影响任何字段。
- 输出可按月→周→日展示，但内部计算顺序可优化；改变输入顺序不得改变身份或内容。

## 5. 身份、幂等与冲突

`evidence_id`由规范化内容中的以下身份字段计算：

```text
gate_event_id + instrument_id + as_of + path_status
+ universe_id + market_snapshot_id + adjustment_policy
+ registry_version + detector_policy_version
+ factor_id + factor_version
```

生成时间不进入身份。同一完整身份重复运行必须得到相同ID和内容；相同身份而内容不同必须报冲突。因子公式变化必须升级`factor_version`或检测政策版本；复权政策、行情快照、GateEvent或因子版本变化必须产生新证据，禁止覆盖旧证据。

一批证据按规范因子ID排序输出，并另算批次内容指纹。排序仅便于审计，不得成为身份的偶然来源。

## 6. 家族、父子与跨周期事实

M04可以保存三类非评分汇总：

- 家族中哪些证据可用、哪些命中；
- 父子依赖是否满足及阻断原因；
- 月／周／日证据是否同时存在及各自日期。

这些都是事实索引，不是加分、共振奖励或排名。风险因子与正向因子分开标识；零权重研究因子仍可见，但M04不解释其生产权重。

CR-033“二次独立三推确认”仍为`deferred`，本设计只提醒未来登记，不把它加入注册表或检测器。

## 7. 旧数据兼容与迁移

- 当前`factor_snapshot.py`、`daily-factor-snapshot.json`、每日扫描、夜间回放及公开输出保持原样。
- 旧嵌套因子只能经过一个只读适配入口转换为legacy证据；适配器不得回写、不得补造不存在的身份或防未来结论。
- `TechnicalEvidence 1.x`可继续只读验证，但不能进入2.x formal消费者。
- M04先在固定小样本和现有2026-08-28旧快照上影子对照。只比较仓库确实保存的命中、可用、日期及证据字段，不宣称不存在的全市场复现。
- 新验证失败不得破坏当前网站或旧生产路径。生产切换、真实Manifest、网站和Discord同源读取仍属于M12。

## 8. 明确不做

M04不：

- 新增、删除或改写因子定义、阈值和当前39项历史快照；
- 计算总分、分项分、权重、加分、封顶或缺失值分数；
- 建立排行榜、精选门槛、交易就绪判断或交易计划；
- 修改复杂多因子或“我最喜欢形态”的业务结果；
- 修改MACD门票、GateEvent、股票池、行情或历史事件；
- 修改生产工作流、公开JSON、网站、Discord或运行真实回测；
- 实施M05—M13或M12生产切换。

后续责任只作引用：M05消费证据做两个选股器，M06保存上下文，M07评分与唯一排行，M08交易计划，M09事件总账，M10评价，M12生产集成。

## 9. 机械验收矩阵

1. 全仓机械清单证明只有一个新`evidence_id`生产入口。
2. 每个注册表有效因子恰好一条证据；数量动态读取，重复或遗漏均失败。
3. 同一输入重复运行以及不同`PYTHONHASHSEED`得到相同证据ID、内容和批次指纹。
4. 每日影子与回放影子对同一`GateEvent + as_of + market_snapshot_id`得到完全相同证据。
5. MACD和既有长期资格使用`gate_reference`，测试证明不会再次调用对应检测公式。
6. 父条件缺失、不可用或未命中时保留`raw_hit`，但`qualified_hit=false`并列出`blocked_by`。
7. 未来日K、未完成周／月周期和未确认pivot不能进入证据。
8. formal缺少Universe、行情或Gate身份时失败；legacy不能被formal入口接受，也不得自动回退。
9. 相同完整身份不同内容报冲突；任何公式或政策变化产生新身份且旧证据不被覆盖。
10. 旧JSON只读适配前后字节一致；无法确认的字段为`unknown`或失败，不猜测。
11. 固定样本逐项对照当前注册表的`available`、命中、日期和值；出现无法解释差异立即停止。
12. 默认每日、夜间、网站、Discord、工作流、公开JSON、评分、排行和交易结果零变化。

## 10. 回退

M04实施期只新增中立合同、唯一生产器和影子调用。任何失败都可停止影子调用并继续使用现有`factor_snapshot.py`；不删除旧入口、不改历史、不覆盖证据。若发现新旧因子事实无法解释地不同，停止在本地审核关，保留反例，不修改旧结果迎合新合同。

## 11. 未来小工作包（均不超过20分钟）

- 包A：冻结规则、`TechnicalEvidence 2.x`、身份和唯一生产者边界。
- 包B：建立`services/factors/`纯生产器、验证器和固定小样本；先证明每项只计算一次。
- 包C：接入父子／家族／周期事实及旧JSON唯一只读适配器。
- 包D：增加每日与回放影子入口，完成新旧事实逐项对照；默认生产路径不变。
- 包E：完整本地验收、独立实现提交和证据文档提交；不部署、不生产切换。

A—E只有在用户批准本设计后才能实施；批准M04不自动批准M05或M12。

## 12. 已批准选择

1. 注册表中已由M03拥有的MACD和长期资格，只生成引用型证据，不重新计算。
2. 新formal合同使用`TechnicalEvidence 2.x`；当前1.x保持legacy只读，禁止自动补齐。
3. M04产物只存在于内存、测试临时目录或被忽略的`work/`影子目录；生产公开JSON切换留给M12。

用户已批准本设计；A—E已完成本地实现和验收。详见`M04_ACCEPTANCE_REPORT_ZH.md`。本地`verified`不等于提交、合并、部署或生产启用。
