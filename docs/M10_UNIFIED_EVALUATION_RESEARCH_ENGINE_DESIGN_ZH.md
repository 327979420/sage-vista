# M10｜统一评价、回测与外部研究引擎设计

- 文档状态：M10-A／B／C／D里程碑均已审核并进入`main`；M10-D在获批查询与审核导出范围内为`implemented`；M10-E已获批准并处于`implementing`；M10整体仍为`implementing`
- 对应需求：`CR-2026-09-02-050`
- 基线提交：`5dfd0a57fc1dad56042c0db6b8e2c3ce9ff88251`
- 设计日期：2026-09-02
- 生产状态：M10-A合同基础、M10-B内部基线评价器、M10-C只读汇总和M10-D查询／审核导出均已进入`main`；未部署、未生产启用

> 本文冻结M10的职责、合同边界、身份和失败关闭语义。M10-A、M10-B、M10-C和M10-D均已完成独立审核并进入`main`，M10整体继续为`implementing`。M10-C只建立Portfolio失败关闭边界和只读研究汇总，不批准资本算法或真实组合表现。M10-D只交付获批的原子库存查询、CSV／XLSX审核副本和导出证据，不代表部署、生产启用或真实历史导出；M10-E最小设计已经用户批准，按E1／E2／E3连续实施。VectorBT、真实多年回测、生产目录、M11和M12仍未批准。

## 1. 人话版

Sage Vista现在像有几位研究员各拿一本不同格式的成绩册：夜间回放、Tracker、因子实验和旧机会账本都算过一些收益，但它们使用的身份、窗口、费用和缺失值说法并不完全相同。数字可以用于旧研究，却不能自动拼成一份“绝对准确”的正式20年成绩单。

M10要做的是先建立同一间考试室：

1. 上游交来已经冻结的股票、事件、排行和交易计划，M10不重做这些判断；
2. 一张运行收据写清楚代码、数据、政策、日期、分区和输入输出指纹；
3. 四种成绩分开保存，不能把“股票后来涨了”冒充“交易计划赚了”，也不能把逐股收益拼成没有资金限制的组合曲线；
4. 内部简单引擎先给出可逐笔核对的基准；VectorBT以后只能拿同一份试卷做comparison；
5. CSV／Excel是从权威账本打印出的审核副本，人在表格里做批注也不能改写机器原件。

一句话职责：

> M10只把M02、M07、M08、M09的不可变事实转成可复现的逐股评价、组合运行和研究汇总；不创造上游事实，不批准新策略，也不接生产。

## 2. 当前机器事实与现状审计

截至本设计基线，生产数据日为2026-08-28；旧历史回放覆盖2025-12-29—2026-08-28，共168个交易日，下一断点为2025-12-22—2025-12-28。来源分别为`automation/production-state.json`、`automation/backtest-state.json`和`automation/backtest-progress.json`。这些只是当前机器状态，不是M10正式评价结果。

| 当前路径 | 现在做什么 | 可复用部分 | 不能直接升级为formal的原因 |
| --- | --- | --- | --- |
| `.github/workflows/nightly-backtest.yml` → `services.scanner.unified_v2_scan` | 按自然周向前回放并合并旧公开结果 | 断点、失败不推进、模型／因子版本 | 仍走legacy扫描链；批次缺完整代码、数据、股票池和输入输出指纹 |
| `research/backtest/tracker_backtest_v1.py` | 生成逐股旧信号、窗口收益、MFE／MAE和止损场景 | 下一调整后开盘、逐股明细 | ticker＋日期身份；没有M02／M08／M09稳定引用；未成熟事件可能被整体省略 |
| `research/backtest/tracker_backtest_v2.py` | 模拟退出并生成汇总 | 止损优先等旧研究行为、源文件哈希 | 逐笔结果未成为不可变合同；无费用／滑点及资本约束 |
| `research/backtest/reused_event_study_v2.py` | 复用旧事件研究多窗口表现 | 点时技术、完整周期、未成熟窗口为`null`、分期研究 | 会用当前缓存复核旧门卫；历史股票池／退市与稳定证券身份不完整 |
| `research/factor_lab/` | 因子、配对、对照及案例研究 | development／validation／forward分区与统计方法 | 输出结构各自定义，未绑定统一逐股结果ID和运行收据 |
| `public/opportunity-ledger.json`、`public/signal-history.json` | 旧生产账本和跟踪结果 | legacy只读对账 | 已混合选择与评价，以ticker＋日期为主，不能补猜新身份 |

当前结论：旧夜间回放属于`legacy`，`research/backtest/`和`research/factor_lab/`属于`research_only`或legacy研究。当前没有任何产物可直接称为formal `ForwardOutcome`、`TradeOutcome`、`PortfolioRun`或`ResearchAggregate`。M02已经证明2026-08-28及更早缺少完整formal股票池证据，因此当前真实历史最多只能得到带偏差的legacy或`unavailable`；固定合成样本只能验证合同能力，不能产出正式多年收益结论。

### 2.1 当前依赖与运行环境

- 仓库没有Python依赖清单或锁文件，也没有现成的VectorBT、NumPy、pandas、openpyxl或XlsxWriter依赖。
- 现有研究入口以`python3 -m ...`、`argparse`、显式路径和JSON为主。
- `work/`、`outputs/`和`dist/`已被Git忽略，适合未来影子中间产物；权威配置和小型证据另行受Git管理。
- 本轮不安装或升级任何依赖，不修改任何工作流。

## 3. 边界与唯一权威来源

未来formal唯一评价生产层建议为：

```text
services/evaluation/
```

它只接收：

- M02：`instrument_id`、formal `UniverseSnapshot`、不可变调整后OHLCV、`market_snapshot_id`、`ADJUSTMENT_POLICY`；
- M07：不可变`ScoreResult`与权威formal `RankingSnapshot`；
- M08：`TradePlan`、完整`ExitState`修订链和执行政策；
- M09：唯一`event_id`、机器引用及追加记录；
- Git提交、版本化评价配置和内容指纹。

它不得：

- 按ticker猜稳定证券身份；
- 重算或修改Gate、因子、模型、上下文、分数、排行、交易计划或退出顺序；
- 把comparison重算写成当时的权威结果；
- 把今天的股票池、ETF成分或行情状态倒填历史；
- 回写M09机器事件或人工记录；
- 写`public/`、`automation/`、网站或Discord；
- 自动启用任何延期持仓／退出实验。

唯一权威不是某一个第三方库，而是：

```text
已验证的上游不可变输入
+ 版本化M10评价政策
+ 不可变运行收据
+ 四类M10结果及内容指纹
```

## 4. 统一运行收据：ExperimentRun 2.x

M01已有`ExperimentRun 1.x`，但只保存较薄的实验状态、证据窗口和输入／结果引用。M10不创建平行的第五种运行合同，而是未来将它显式升级为`ExperimentRun 2.x`：

- `experiment_id`：预登记研究问题的稳定身份；
- `run_id`：一次精确执行的不可变身份；
- `schema_version`、`source_version`、`evaluation_policy_version`；
- `path_status`：`formal`或`legacy`；
- `result_role`：`authoritative`或`comparison`；
- `partition_role`：`development`、`validation`或`forward`；
- 精确代码提交、配置ID／版本／SHA-256；
- 引擎名称、引擎版本和适配器版本；
- M02／M07／M08／M09输入ID与指纹；
- 数据范围、交易日历身份、复权／费用／滑点政策；
- 输入清单、输出清单、逐文件大小和SHA-256；
- 启动／完成时间、状态、错误类别、偏差标签和不可重建区间；
- 断点运行的父收据或上一成功检查点身份。

`ExperimentRun 1.x`只能legacy只读。缺少任何formal必填证据时，运行收据必须为失败、`unavailable`或legacy，不得补造。

`future_data_used`必须相对于运行收据的`evidence_as_of`解释：信号生产不得使用信号日后的事实，但Forward／Trade评价按获批窗口观察后来已经成熟的行情不是“偷看未来”。观察窗口、数据可得时间和评价生成时间必须分别保存，不能只写一个容易误解的布尔值。

`run_id`来自规范化身份字段，不包含易变的显示文字或生成时间。相同身份与相同内容是幂等重放；相同身份与不同内容必须冲突失败。失败和中断收据同样只追加保留。

## 5. 四类结果合同

四类结果共享以下元数据：

- 纯SemVer `schema_version`；
- `run_id`以及适用于该类结果的稳定主体引用；
- `path_status`、`result_role`、`partition_role`；
- `evaluation_policy_version`和规范化输入指纹；
- M02／M07／M08／M09所需的上游稳定ID；
- 状态、偏差、缺失事实及内容SHA-256。

不是每类结果都机械要求所有ID。逐股结果保存`instrument_id`和`signal_date`；PortfolioRun绑定一组结果ID而不是一个股票事件；没有计划的ForwardOutcome不得伪造`trade_plan_id`。M09根事件只覆盖M07权威主榜入榜项；研究“落选后大涨”时，可以绑定M07已验证的排除主体引用，但没有`event_id`的结果只能是明确comparison，不能伪造M09事件或进入formal权威事件历史。

### 5.1 ForwardOutcome 2.x

回答：“信号以后固定交易日窗口的客观价格表现怎样？”它不代表真正执行了交易。

每条记录只绑定一个稳定主体和一个固定交易日窗口，便于窗口成熟后只追加结果，不覆盖其他窗口。最小字段：

- `forward_outcome_id`、主体类型、M09 `event_id`或M07排除主体引用、`instrument_id`、`signal_date`；
- 窗口政策、交易日历／session覆盖政策版本和`window_sessions`；
- 起算规则、起算交易日和调整后价格；
- 终点交易日和调整后价格；
- 区间收益、MFE、MAE；
- `price_basis`、M02完整`ADJUSTMENT_POLICY`、行情快照及内容指纹；
- `pending`、`mature`或`unavailable`状态；
- 缺失、停牌、退市、交易日历及数据修订证据。

首版窗口已经冻结为`1／5／20／60／100`交易日。起算口径保持当前可审计基线：信号日收盘确认后，以第一根真实可用的下一交易日调整后开盘价为起点，第N个交易日的调整后收盘为N日终点；这只是客观观察基准，不代表真实成交。调用层必须注入带版本和指纹的预期session序列，M10不能把“出现了N根K线”自行解释成“走满N个交易日”。目标session尚未到达`evidence_as_of`时必须为`pending`。目标已经到期但起点或终点缺失时为`unavailable`；起点和终点存在但中间路径不完整时可为`partial`，终值收益可保存但MFE／MAE保持不可用，均不得猜价格。

`SessionCalendarEvidence`只能保存信号日之后且不晚于`evidence_as_of`的已发生session前缀，禁止保存或推算未来session。对窗口N，只有当前缀长度达到N时，`target_session_date`才等于`sessions[N-1]`；否则该字段必须为`null`，状态必须为`pending`且不得保存端点日期或价格。目标日已经发生但行情缺失时可以保存该目标日，端点仍为`null`，不得用相邻日期替代。

ForwardOutcome版本边界固定如下：旧`2.0.0`严格保持原字段集合，不允许`target_session_date`，只作既有记录的只读验证；新internal-baseline formal生产器只生成`2.1.0`，其中`target_session_date`为必填但可空字段，新formal完成流程拒绝`2.0.0`或混合版本。目标日进入具体结果身份、输入指纹、内容指纹及pending预期结果描述，但不进入`logical_result_id`，因此同一事件与窗口由未成熟到成熟仍走同一追加修订链。该结构升级对应内部基线来源版本`m10-b-internal-1.1.0`。

每个窗口有稳定`logical_outcome_id`。较早`pending`记录和后来成熟记录都是不可变版本；成熟版本通过`supersedes_outcome_id`指向直接前一版本，旧记录不得删除或覆盖。

禁止放入：模拟成交、交易计划收益、组合资金曲线、评分或人工结论。

### 5.2 TradeOutcome 2.x

回答：“严格执行已经获批的M08计划和退出状态后发生了什么？”

最小字段：

- `trade_outcome_id`、`event_id`、`trade_plan_id`、完整ExitState链及唯一终态`exit_state_id`；
- `instrument_id`、`signal_date`、计划／执行政策版本；
- 实际模拟入场交易日和调整后开盘价；
- 冻结的止损、目标、期限及其上游证据引用；
- 退出交易日、调整后执行价、原因和持仓交易日数；
- 毛收益、净收益、R收益、MFE、MAE；
- 费用／滑点政策版本和逐项金额；
- `price_basis`、M02复权政策、行情快照和修订身份；
- `completed`、`open`、`no_trade`或`unavailable`及明确原因。

M10只读取M08已经决定的下一真实开盘、跳空止损、普通止损／目标、同日止损优先和期限退出顺序，不再模拟另一套退出。调用者必须注入并完整验证ExitState修订链，M10不得按文件顺序、生成时间或M09关联记录的`as_of`猜终态。若M08未形成计划，保留`no_trade`或`unavailable`，不能删除样本。由于退出日MFE／MAE纳入口径尚未单独获批，首版B只保存`mfe_status/mae_status=unavailable`及明确原因，不顺手冻结legacy口径。

formal TradeOutcome可以保存可复核毛收益。费用和滑点政策尚未批准时，formal `net_return_status`必须为`unavailable`且`net_return=null`；零成本净收益只能产生身份明确的`comparison`结果，不能冒充formal权威净收益。

禁止放入：新的入场／退出策略、延期实验、组合仓位、排行重算或人工修正。

### 5.3 PortfolioRun 2.x

回答：“在明确资本和并发约束下，整套组合如何运行？”

M10-C不批准资本、仓位、并发或信号竞争政策，因此它只建立失败关闭的Portfolio边界，不建立组合算法：

- 现有`PortfolioRun 2.0.0`及其`portfolio_policy_not_approved`原因保持原字段和原字节只读，不原地改义；
- 新formal M10-C若保存Portfolio边界，使用`PortfolioRun 2.1.0`，状态只能为`unavailable`，原因必须精确为`capital_allocation_policy_not_approved`；
- 只允许保存运行身份、政策证据、规范排序后的完整TradeOutcome ID／内容指纹集合、集合指纹、状态和内容指纹；输入必须是已通过同一M10合同验证入口验证的完整TradeOutcome对象，不能接受调用者自行拼出的裸引用；
- 重复结果ID、同一`logical_result_id`的多个修订、错误引用、跨角色／分区／政策或ID与内容指纹不一致均失败关闭；
- 同一规范化输入集合与政策只对应同一身份，输入顺序不得改变ID或内容；旧边界记录只追加，不覆盖。

`PortfolioRun 2.1.0`明确禁止初始资本、仓位、现金、持仓、市值、权益曲线、组合总收益、年化收益、最大回撤、信号竞争、最大持仓和资金不足处理字段。任何旧脚本的非重叠cohort或独立逐股收益拼接只能标记为研究诊断，不能冒充资本受限组合曲线。

### 5.4 ResearchAggregate 2.x

回答：“一组已经冻结、口径一致的逐股结果呈现什么最小客观统计？”

现有`ResearchAggregate 2.0.0`继续作为`research_aggregate_not_implemented`的只读骨架，不能在原版本上增加字段或改变引用语义。新formal M10-C固定使用`ResearchAggregate 2.1.0`及来源版本`m10-c-readonly-1.0.0`，由`services/evaluation/`内唯一只读汇总生产器生成；每日与回放未来只能通过薄入口调用同一纯函数。本设计提交本身不实现该生产器，后续获批实现仍不接生产。

#### 5.4.1 输入边界

- 一份汇总只能消费一种经过完整验证的不可变结果：全是`ForwardOutcome`，或全是`TradeOutcome`；M10-C不汇总`PortfolioRun`，也不允许两种逐股结果混合。
- Forward汇总必须固定一个`window_sessions`，不得把1／5／20／60／100日混成一个数字；Trade的`window_sessions`固定为`null`。
- 输入必须在`path_status`、`result_role`、`partition_role`、评价政策、分区政策、M02复权／数据政策上完全一致；Forward还必须统一窗口政策，Trade还必须统一执行政策和成本证据状态。不同日期的合法行情快照可以不同，但不得混用数据政策。
- 生产器接收完整Outcome对象，先调用现有唯一合同验证入口，再从对象派生规范排序的结果ID／内容指纹引用；裸引用、重复结果ID、同一`logical_result_id`的多个修订、错误角色、内容指纹冲突均失败关闭，不能自动猜测当前修订。
- 允许以明确、严格白名单的`aggregate_scope`表达空样本范围；它只包含结果类型、Forward窗口、path／role／partition及必要政策身份，不是自由格式查询、行情或重算容器。
- 输入结果ID、内容指纹、规范化集合指纹和聚合政策必须完整保存并参与身份；输入顺序不改变汇总身份或数字。

#### 5.4.2 最小输出字段

除公共身份、运行收据、来源版本、修订链和内容指纹外，`ResearchAggregate 2.1.0`只允许：

- `source_result_type=forward_outcome|trade_outcome`、`window_sessions`和严格白名单的`aggregate_scope`；
- `aggregation_policy`、规范排序后的`result_refs`及集合指纹；
- `total_count`、严格按结果类型定义的`status_counts`、`evaluated_count`、`missing_count`和`missing_rate`；
- `win_count`、`loss_count`、`flat_count`、`win_rate`；
- `mean_gross_return`、`median_gross_return`、`gross_profit`、`gross_loss_abs`、`profit_factor`、`gross_expectancy`；
- `metric_status`和`metric_reason`。

Forward的`status_counts`必须精确且只包含`pending/mature/partial/unavailable`；Trade的`status_counts`必须精确且只包含`completed/open/no_trade/unavailable`。现有TradeOutcome用`status=pending + status_reason=trade_open`表达未退出交易，汇总器必须将且只能将这个已验证组合映射为`open`桶；该规范桶不修改上游TradeOutcome合同，也不能被静默并入普通pending。`no_trade`同样不得删除或并入`unavailable`。所有键即使计数为0也必须存在，禁止自由增加状态键。

统一守恒为：`total_count`等于输入结果总数，也严格等于`sum(status_counts.values())`；`evaluated_count`只统计真实存在且允许参与汇总的有限`gross_return`；`missing_count=total_count-evaluated_count`，并满足`total_count=evaluated_count+missing_count`及`win_count+loss_count+flat_count=evaluated_count`；`total_count>0`时`missing_rate=missing_count/total_count`，否则为`null`。Forward mature且有毛收益时进入统计；partial仅在真实毛收益存在时进入，没有毛收益的partial计入`missing_count`；pending与unavailable不进入。Trade completed且有毛收益时进入；open、no_trade和unavailable分别计数并全部进入`missing_count`，不能被当成0收益。

#### 5.4.3 唯一计算口径

- Forward和Trade都只读取Outcome已冻结的`gross_return`，不得生成formal净收益汇总；没有费用／滑点政策时尤其不得以零成本替代。
- `win/loss/flat`以规范化Decimal值严格按大于0／小于0／等于0分类；`win_rate=win_count/evaluated_count`，平收益保留在分母。
- `gross_profit`是所有正收益之和；`gross_loss_abs`是所有负收益绝对值之和，保存为非负数；`profit_factor=gross_profit/gross_loss_abs`。
- `mean_gross_return`为可评价收益算术平均；中位数按收益排序，偶数样本取中间两项平均；首版`gross_expectancy`严格等于同一量化后的`mean_gross_return`，不维护第二套公式。
- 任何缺失值都不能作为0收益参与分类、分母或金额合计；状态守恒按上一节的`status_counts/evaluated_count/missing_count`机械验证。
- 所有输入先以`Decimal(str(value))`规范化，输出沿用M10内部基线的`1e-10`量化和`ROUND_HALF_EVEN`；不得用二进制浮点格式化值参与分类、身份或业务判断。
- 新增唯一`aggregation 1.0.0`政策，只冻结上述纳入、分母、精度、中位数和Profit Factor语义，不引入评分、策略或自由公式。

ResearchAggregate不能读取M02行情、重算逐股收益、反向修改逐股结果或M07—M09，也不能用新行情重算后保留旧ID。分数单调性、因子lift、Pair Matrix、组合统计和跨分区稳定性全部延后，不属于M10-C。

## 6. 数值与失败关闭语义

### 6.1 时间和价格

- 信号日判断只读取截至该日已完成的数据；forward价格只能在对应交易日真实成熟后追加。
- 所有窗口按版本化交易日历计数，不按自然日猜周末、假期或停牌。
- M08下一交易日调整后开盘规则保持不变；M10保存`price_basis`，不得冒充券商真实成交。
- 复权政策必须完整引用M02 `ADJUSTMENT_POLICY`。政策或行情修订变化产生新结果身份／修订链，不原地覆盖。
- 停牌、退市、缺失或不完整行情必须保存明确状态和可用覆盖，不能删掉难看或无法计算的样本。
- 当前股票池／ETF成员倒填历史时只能legacy或`unavailable`，不能产生formal结果。

### 6.2 费用、滑点和执行

- 费用、滑点、持仓期和执行顺序必须分别版本化。
- 没有获批费用／滑点政策时，formal可保存毛收益，但`net_return`必须为`null`并明确`unavailable`；零成本净收益只允许明确的comparison角色。
- M08计划和退出状态是执行事实唯一来源。M10只计算结果，不改变止损、目标、同日顺序或退出日期。

### 6.3 空样本与特殊数值

JSON不得写`NaN`、`Infinity`或`-Infinity`。M10-C冻结以下机械语义：

| 情况 | `profit_factor` | 状态说明 |
| --- | --- | --- |
| 没有可评价样本 | `null` | `metric_status=unavailable`、`metric_reason=empty_sample`；所有收益统计为`null` |
| 有正收益且`gross_loss_abs=0` | `null` | `metric_status=available`、`metric_reason=unbounded_no_losses`，不能写Infinity |
| 没有正收益但存在亏损 | `0.0` | 有限、可解释的零 |
| 全部可评价结果恰为0 | `null` | `metric_status=available`、`metric_reason=undefined_zero_profit_and_loss` |
| 输入包含非法非有限数 | 无结果 | 验证失败，不落权威产物 |

没有可评价样本时仍保存`total_count/status_counts/missing_count`：`total_count>0`则`missing_rate=1`，`total_count=0`则`missing_rate=null`。Forward pending／unavailable和Trade open／no_trade／unavailable不进入收益分母；Forward partial只有存在真实有限`gross_return`时才进入。没有证据时写`null + status/reason`，不得用0掩盖缺失。

## 7. 版本、角色与历史保护

- `path_status=formal|legacy`说明输入证据质量；formal缺证据不得自动退回legacy。
- `result_role=authoritative|comparison`说明结果是否代表当时获准政策；comparison不得写入当时权威历史。
- `partition_role=development|validation|forward`由版本化分区政策决定，同一事件不得跨分区重复冒充独立证据。
- V1和V2以明确政策版本、生效日和输入指纹区分。V2在其生效日前重算旧日期只能产生comparison。
- 旧结果不可覆盖；合法数据修订或政策变化产生新ID，并用`supersedes_result_id`或运行收据引用旧版本。被替代记录仍可审计。
- formal消费者只接受已知主版本。旧M10 1.x或旧研究JSON只能经唯一只读适配器进入legacy查询，不能猜造稳定ID后升级。

## 8. 外部研究引擎适配

未来中立接口建议为：

```text
M09事件 + M08计划 + M02行情
→ M10标准数据集适配器
→ Sage Vista内部基线引擎
→ 可选BacktestEngineAdapter
→ 逐笔对账
→ 标准M10结果合同
```

`BacktestEngineAdapter`只接收同一份已验证、不可变的标准数据集，并返回可映射到M10合同的逐笔结果。内部基线引擎是最小、可解释的对账基准，不是第二套上游事实生产者。

VectorBT适配器必须遵守：

- 不重新定义Signal、Gate、因子、评分、排行、TradePlan或退出顺序；
- 不通过Yahoo、EODHD或其他接口自行下载行情；
- 不直接写M09、生产JSON或公开目录；
- 在逐笔完全对账前固定`result_role=comparison`；
- parity至少逐项比较事件、入场、退出、价格、费用、毛／净收益、R、MFE和MAE；
- 差异必须形成报告，不能用容差静默吞掉业务差异；
- 不进入网站、Cloudflare或默认夜间运行环境；
- 优先锁定官方发行版，不默认fork；只有确需维护上游补丁且单独批准时才考虑fork。

### 8.1 依赖与许可证闸门

截至2026-09-02，VectorBT官方PyPI版本为1.1.0，声明支持Python`>=3.11,<3.15`。它的基础安装已经引入NumPy、pandas、SciPy、Numba、Plotly、Jupyter组件和scikit-learn等依赖；`full`／`rust`会继续扩大范围。因此未来X1包必须建立项目自己的依赖清单、精确版本／哈希证据和安全检查，首轮禁止`vectorbt[full]`。

VectorBT 1.1.0许可证为Apache 2.0加Commons Clause。未来商业、收费托管、再分发或客户交付前必须再次由适当责任人核验许可范围；本设计只登记风险，不作法律结论或安装决定。权威来源：

- <https://pypi.org/project/vectorbt/>
- <https://github.com/polakowo/vectorbt/blob/v1.1.0/pyproject.toml>
- <https://github.com/polakowo/vectorbt/blob/v1.1.0/LICENSE.md>

## 9. 配置与统一CLI

### 9.1 现状和唯一职责

当前`research/backtest/`保留多种独立研究脚本：有的直接调用计算函数，有的用各自的`argparse`参数和固定输出路径；`tracker_backtest_v1`、`trailing_stop_v1`等仍带开始日期、缓存、旧公开账本或输出目录默认值，年度／因子实验也各自解释输入目录和年份。`factor_strategy_lab_v2`等会读取既有事件／行情缓存、计算研究结果并写文件。`services.scanner.backtest_progress`还可按默认路径读取公开报告并写入`automation/backtest-state.json`和镜像；`experiment_catalog`按固定账本生成研究目录，并在缺历史事件时间时使用当前时间作为目录生成时间。范围内未发现问答式`input()`，但“默认路径、当前时间、固定文件和脚本内参数”仍不能组成一份可复现的M10正式运行配置。

这些旧入口继续作为明确legacy研究或生产工具保留，不在M10-E删除、迁移或改写。尤其M10-E不得调用`services.scanner.backtest_progress`推进旧夜间断点，也不得把旧脚本包装后称为formal。

M10-E的唯一职责是：

> 使用一份不可变、版本化JSON配置，非交互地调用M10-A—D现有公共接口，建立可追溯运行收据，保存失败或中断状态，并仅从配置明确引用的检查点继续。

首版使用入口：

```text
python3 -m research.run --config <versioned-config.json>
```

`--config`是唯一可改变业务语义的命令行输入。CLI不得询问用户、读取环境变量决定日期／版本／政策、按文件名猜证券或版本，也不得寻找“最新配置、最新结果、当前分支、今天或最新Manifest”。stdout只输出一行或一个小型规范JSON摘要，诊断写stderr；稳定错误类别映射稳定非零退出码。CLI只做解析、验证、编排和守恒检查，不包含评价、汇总、查询或导出算法。

### 9.2 `ResearchRunConfig 2.0.0`

M10-E首版formal配置合同固定为`ResearchRunConfig 2.0.0`，来源版本固定为`m10-e-cli-1.0.0`，只允许一个创建／规范化函数和一个公共验证入口。顶层采用严格字段白名单：

- `schema_version`、`source_version`、`config_id`、`config_content_fingerprint`；
- `operation_type`：只允许`forward_evaluation`、`trade_evaluation`、`portfolio_boundary`或`research_aggregate`之一；一份配置只产生一种M10权威结果族，防止把不同ExperimentRun语义揉成一条收据；查询／导出只能作为完成后的显式`export_plan`；
- `path_status`、`result_role`、`partition_role`、`bias_labels`；
- `as_of`与`evidence_window.start/end`；
- `universe_ref`、`market_snapshot_ref`和M02 `adjustment_policy_ref`；不适用的操作必须明确为`null`，不得省略或伪造；
- `selection_refs`：显式M07排行和／或M09事件稳定ID与内容指纹；
- `execution_refs`：Trade操作所需的M08 TradePlan和ExitState稳定ID与内容指纹，其他操作必须为空；
- `input_selector`：只能二选一为规范排序的显式引用集合，或一个完整且重新验证的`EvaluationQuery 2.0.0` payload；只有Query ID及指纹而没有查询条件不足以解析输入；禁止裸ticker和动态查询；
- `policy_refs`：按操作精确包含evaluation、partition、adjustment、forward_window、execution、cost_slippage或aggregation引用；不允许重复kind或未知政策；
- `engine`与`producer_source_version`：必须精确匹配已批准的M10-B或M10-C引擎／来源，M10-E本身不成为结果生产引擎；
- `output_contract`：结果合同名、严格schema版本及来源版本；不得写“2.x”或“latest”；
- `storage`：明确`root_kind`和规范路径。只允许系统临时目录或仓库已忽略的`work/`子目录，两者均为影子存储；禁止`public/`、`automation/`及生产目录；
- `export_plan`：`enabled`、完整且重新验证的`EvaluationQuery 2.0.0`和`ExportConfig 1.0.0` payload及其ID／指纹、格式集合及导出根；关闭时其余字段必须为`null`；
- `resume`：`mode=fresh`时父运行与检查点均为`null`；`mode=checkpoint`时必须同时给出`parent_run_id`、`checkpoint_id`及内容指纹；
- `work_units`：调用者显式给出的有序日期分区；首版不替用户决定真实多年批次大小；
- `expected_results`：结果合同、schema、每个work unit的逻辑全集规则；Forward固定每事件`1/5/20/60/100`五个窗口，Trade每个可评价计划一项，C层按现有合同一项；
- `code_commit`：完整40位提交。formal执行时必须等于实际HEAD且工作区／暂存区干净。

配置使用拒绝重复键和NaN／Infinity的严格JSON读取器。v2不接受自由浮点数；计数使用整数，需要Decimal的未来字段只能使用规范十进制文本。`config_id`和`config_content_fingerprint`由同一个规范语义函数计算，排除自身两个派生字段；配置没有`generated_at`。任一日期、角色、政策、版本、引用、路径、work unit或提交变化都改变身份，相同`config_id`不同内容失败。

集合型数组`bias_labels`、稳定输入引用、政策引用和导出格式按各自稳定键去重排序；顺序型`work_units`保持调用者顺序并进入身份。配置文件运行中只读，不补写解析后的输入、结果ID或运行时间。大型输入可由精确查询引用解析，但pending收据必须冻结实际解析出的完整输入ID／内容指纹全集和预期逻辑结果全集。

操作与既有输入输出固定如下；M10-E不得增加第五种结果合同：

| `operation_type` | 必需的已验证输入 | 唯一结果合同／来源 | 现有生产入口 |
| --- | --- | --- | --- |
| `forward_evaluation` | M09事件、M02行情／股票池／复权和权威session日历 | `ForwardOutcome 2.1.0`／`m10-b-internal-1.1.0` | `evaluate_forward_baseline` |
| `trade_evaluation` | M09事件与机器链接、M08计划／ExitState、M02行情／股票池／复权 | `TradeOutcome 2.0.0`／`m10-b-internal-1.1.0` | `evaluate_trade_baseline` |
| `portfolio_boundary` | 当前唯一叶节点的已验证TradeOutcome | `PortfolioRun 2.1.0`／`m10-c-readonly-1.0.0` | `evaluate_portfolio_boundary` |
| `research_aggregate` | 同一口径、同一结果类型的当前唯一叶节点 | `ResearchAggregate 2.1.0`／`m10-c-readonly-1.0.0` | `evaluate_research_aggregate` |

### 9.3 复用现有A—D公共接口

M10-E只能调用下列现有边界：

- A：`build_experiment_run_receipt`、`validate_experiment_run`、结果合同验证、`current_result/current_experiment_run`和`EvaluationShadowStore`；
- B：`evaluate_forward_baseline`、`evaluate_trade_baseline`及其batch验证／保存入口；
- C：`evaluate_portfolio_boundary`、`evaluate_research_aggregate`及其batch验证／保存入口；
- D：`build_evaluation_query`、`execute_evaluation_query`、`build_export_config`、`publish_audit_export`和`verify_export_package`。

一份配置只选择一个`operation_type`，从而直接沿用相应生产器的一种ExperimentRun和结果守恒。需要“Forward／Trade → Aggregate → 导出”时使用显式、互相引用的版本化配置链；后一步必须引用前一步已经落盘且重新验证的结果，不能在CLI内部创造跨结果族总收据。M10-D导出可作为完成后显式副作用，但其失败状态与评价完成状态分开。

### 9.4 生命周期和机器摘要

固定流程为：

```text
严格读取并验证配置
→ 解析、逐条验证并冻结全部稳定输入
→ 检查Git和安全存储根
→ 写入pending ExperimentRun收据
→ 调用唯一M10-B或M10-C生产器
→ 验证并只追加保存结果
→ 核对预期逻辑结果全集
→ 追加completed／failed／interrupted收据
→ 若显式开启，再调用M10-D查询和导出
```

- 没有实际落盘pending不能completed；complete必须直接承接同一run唯一pending链尾，且结果缺失、重复、多出、跨run或跨政策均失败。
- `failed`表示输入、合同、身份、证据或守恒的确定性失败；`interrupted`表示超时、进程信号或外部资源中断。两者都用ExperimentRun现有终态追加，保留已成功落盘的不可变结果，绝不覆盖或删除。
- 同一配置和相同解析输入得到相同run根。完全相同记录幂等；同身份不同内容冲突。并发相同formal运行由现有store级inventory锁和run／chain锁序列化，只有一条权威链可完成；第二调用只能验证并返回既有完成事实，或明确冲突。
- 可选导出发生在评价completed之后。导出失败只在CLI摘要中报告`evaluation_status=completed/export_status=failed`，不能倒改评价收据或结果，也不能留下M10-D半包。
- stdout摘要至少包含`run_id`、`config_id`及指纹、status、path／role／partition、输入数、结果数及状态计数、checkpoint或稳定错误类别、存储根，以及可选`export_id/export_receipt_id`；这些数字必须从已验证落盘记录重读，不信任内存计数。

### 9.5 检查点和显式续跑

现有`ExperimentRun 2.0.0`已有`parent_run_id`和`checkpoint_ref`，但`checkpoint_ref`只有ID与指纹，`EvaluationShadowStore`也没有可验证的检查点payload；它不能独立证明完成／待处理分区。因此实施时所需的最小合同变化是增加一个纯编排证据`ResearchRunCheckpoint 2.0.0`及唯一验证／只追加存储入口，不修改ExperimentRun或任何结果语义。检查点只保存：自身ID／内容指纹、config引用、父run及终态收据、规范有序的work unit全集、已完成／待处理分区、已保存结果ID／指纹集合、数据／股票池／政策／代码提交证据和生成时间；不保存行情、不计算结果。

续跑必须由新的不可变配置显式给出父run和checkpoint；配置身份因此变化，新ExperimentRun通过`parent_run_id`连接旧的`interrupted`或`failed`运行。启动前重新验证配置、提交、数据、股票池、政策、检查点内容、已保存结果、已完成和待处理分区的无重叠并集守恒。证据变化时必须新建独立运行或批准的结果修订链，不能修改旧run。已完成结果只验证和引用，不重算；缺失分区必须留在待处理集合，不能静默跳过。

若进程在写终态前突然退出，原pending和已保存结果照常保留；再次执行同一精确配置可按确定run ID重读并核对该run，而不能搜索“最近一次”。跨run续跑仍必须使用显式检查点。`automation/backtest-state.json`和`automation/backtest-progress.json`完全属于legacy夜间生产状态，M10-E不得读后自动选断点，也不得写入或推进它们。真实多年分块大小继续`deferred`。

### 9.6 formal、legacy和生产边界

formal不得含`latest`、`today`、`current_branch`、`latest_manifest`等动态别名，不得引用legacy证据或脏提交；失败后禁止自动改成legacy／comparison。legacy旧入口继续独立运行和留档，不通过M10-E自动升级。M10-E不读取或下载EODHD，不实现网络客户端、Gate、因子、模型、排行、交易、Portfolio资本、收益、查询、导出或Excel导入逻辑，也不接Actions、每日／夜间、网站、Discord、`public/`或生产Manifest。

M10-E是M10核心A—E的最后阶段；只有它以后获得实施授权、通过独立审核并进入`main`，M10核心才可治理收口。VectorBT X1—X3是独立可选comparison扩展，未实施不阻止M10核心收口；本轮不安装、fork、设计适配器或确认商业许可。

### 9.7 最小验收矩阵和工作包

| 编号 | 机械场景 | 必须结果 |
| --- | --- | --- |
| M10-E-01 | 同配置与同输入重放；调换集合型数组顺序 | config／run根和结果一致且幂等；顺序型work unit变化则身份变化 |
| M10-E-02 | 改日期、版本、政策、提交、输入引用或存储／导出配置 | `config_id`改变；旧ID配新内容失败 |
| M10-E-03 | formal含动态别名、重复键、非有限数、缺证据、脏Git或legacy输入 | CLI在写pending前失败关闭，不自动回退 |
| M10-E-04 | 绕过pending；结果缺失、重复、多出、跨run或跨政策 | 不能completed，既有字节不变 |
| M10-E-05 | 明确中断；按错误配置／正确配置引用检查点续跑 | 中断证据永久保留；错误续跑拒绝；正确续跑只处理待处理work unit |
| M10-E-06 | 两个并发相同formal配置 | 最多一条权威链完成，无分叉、覆盖或半写入 |
| M10-E-07 | 单批与显式多work-unit配置调用同一种结果族 | 都通过同一CLI编排和同一A—C生产器，不产生第二套算法 |
| M10-E-08 | 评价成功后导出故障 | 评价仍为completed，导出明确failed且M10-D无半包 |
| M10-E-09 | stdout摘要与落盘收据／结果不一致攻击 | 重读守恒失败；摘要不能伪造数量、状态或路径 |
| M10-E-10 | 尝试网络、生产路径、旧断点推进、Excel回写或第二算法 | 明确拒绝；生产和legacy状态零变化 |

用户已批准连续实施三个独立包：E1只做配置合同、严格JSON、规范身份和固定样本；E2只做统一非交互CLI及pending→results→terminal编排；E3只做检查点／显式续跑、并发守恒和可选M10-D导出闭环。每包单独测试、提交和审核，不运行真实多年回测。

## 10. 存储、查询与导出

| 内容 | 未来位置／形式 | 权威性 |
| --- | --- | --- |
| 运行收据、逐股结果、汇总 | 只追加JSON／JSONL及run manifest | 权威机器证据 |
| 研究配置 | Git版本化JSON | 权威可复现输入 |
| 大型可再生成中间缓存 | `work/`或系统临时目录 | 非权威，可删除重建 |
| CSV／Excel | 从权威结果按export config生成 | 审核副本，不是账本 |
| M12看板数据 | 预计算的小型只读JSON | 可再生成视图 |
| `public/` | 本轮禁止写入 | 生产集成留给M12 |

查询层必须按稳定ID、政策版本、日期、instrument、事件、运行、窗口、状态、路径、角色和分区过滤；不能靠文件名中的ticker和日期猜身份。现有M10结果并不直接保存统一的`strategy_version`、排名或ticker；相关信息只能通过已验证的M09事件和M07排行稳定引用追溯，不能把M10 `source_version`误当策略版本。

### 10.1 M10-D唯一职责与合同

M10-D的D1／D2／D3最小边界已经批准：只在现有`services/evaluation/`和`EvaluationShadowStore`之上增加一个只读查询入口，例如`services/evaluation/query.py`。它不得建立第二数据库、可变“最新结果”索引或新的收益事实。JSON中的M10结果和ExperimentRun收据继续是权威机器证据；查询结果、CSV和XLSX均为可删除重建的审计证据或副本。

获批合同及来源版本如下：

| 合同／配置 | 版本 | 身份职责 |
| --- | --- | --- |
| `EvaluationQuery` | `2.0.0` | 规范化过滤条件、显式修订模式和排序政策；`generated_at`及输出路径不入身份 |
| `QueryResultSet` | `2.0.0` | 绑定查询、一次原子库存快照及规范排序后的精确结果引用集合 |
| `ExportConfig` | `1.0.0` | 固定格式、列、空值、文本安全、精度、布局和分片政策 |
| `ExportManifest` | `2.0.0` | 绑定结果集、导出配置、实际文件／工作表、行数、字节数和SHA-256 |

M10-D来源版本固定为`m10-d-query-export-1.0.0`。这些合同只保存查询与导出证据，不属于第五种收益结果，也不得取代现有`ExperimentRun 2.x`。D1不把这些新引用强塞进当前不支持它们的ExperimentRun 2.0白名单：`QueryResultSet`自身保存查询、库存、代码提交、状态和诊断，`ExportManifest`自身作为成功导出的完整收据。若以后要求查询／导出也进入统一ExperimentRun，必须另行批准并版本化扩展稳定引用角色，不能假称现有合同已经支持。

### 10.2 查询过滤、修订模式和库存证据

`EvaluationQuery 2.0.0`的合同头保存自身`schema_version/source_version/query_id/query_content_fingerprint`；严格`filters`对象另用不会与合同头重名的允许字段，至少包括：

- `result_contracts`、`result_schema_versions`、`result_source_versions`；
- `run_id`、`event_id`、`instrument_id`；
- 独立且包含两端的`signal_date_from/to`与`as_of_from/to`，不得用一个含糊“date”字段；
- `window_sessions`、`status`、`path_status`、`result_role`、`partition_role`；
- 评价、窗口、执行、成本、复权与聚合政策的角色、版本及内容指纹；
- `bias_labels`，首版语义固定为结果必须包含全部请求标签；
- 必填`revision_mode`和固定`sort_policy_version`。

数组输入先按规范值排序和去重，因此输入顺序不影响`query_id`；`null`表示不使用该过滤器，空数组非法，避免“空数组表示全部还是零结果”的歧义。每个过滤器只匹配该结果合同直接保存的字段；字段不存在即不匹配，禁止为凑查询结果隐式遍历M07／M09或猜造派生字段。ticker不是formal查询身份：调用方若使用ticker，必须先经M01稳定证券身份解析；零个匹配返回`unavailable`，多个匹配返回`ambiguous`，均不得猜测instrument。未来如需展开M07／M09细节，必须是显式enrichment，交付并验证完整不可变对象，将其ID／内容指纹和enrichment政策纳入查询身份；D1不实现该展开。

`revision_mode`没有默认值，也没有含糊的`latest`：

- `all`：在验证完整修订链后返回符合过滤条件的全部结果修订，包括已被替代的`pending`、`partial`和`unavailable`；`failed`只属于关联ExperimentRun收据，不得伪造成四类结果状态；
- `current`：先验证每个`logical_result_id`的完整链并调用现有唯一`current_result()`选择唯一叶节点，再应用日期、状态等记录级过滤。禁止先过滤后让旧`pending`重新冒充current。

查询必须先在存储公共入口内建立一次只读库存屏障，并在同一保护范围中冻结`source_inventory_id`和`source_inventory_fingerprint`。库存证据由规范排序的相对路径、合同、稳定ID、内容指纹、文件字节SHA-256、完整规范payload及关联运行收据组成；完整payload是离线重新执行查询所需的最小只读证据，不是第二份可写账本。所有M10写入入口必须参加同一屏障，查询不能在并发写入中拼出混合时点。查询生成和复核共同调用唯一确定性推导函数：先逐条调用现有`validate_result()`／`validate_experiment_run()`并复核路径、文件字节和指纹，按完整逻辑根调用`current_result()`／`current_experiment_run()`，再执行`all/current`、过滤和稳定排序。复核必须把重新推导的完整有序集合与`QueryResultSet`逐项精确比较；少、多、重复、替换或乱序均失败。缺少完整payload时返回`inventory_evidence_unavailable`；损坏ID／内容指纹、重复身份、未知版本、断链、分叉或循环使整次formal查询失败，不能静默跳过坏文件。

现有存储没有M10-D启用前的历史库存快照，因此`as_of`只表示结果的证据日期，不能倒推“过去某个墙钟时刻磁盘中有哪些文件”。这类请求必须返回`historical_inventory_unavailable`；不得按`generated_at`猜库存历史。

`QueryResultSet 2.0.0`至少保存`query_id`及查询内容指纹、库存ID／指纹、代码提交、规范排序的`{result_contract,schema_version,result_id,logical_result_id,run_id,content_fingerprint}`引用、精确`run_receipt_refs`、匹配数量、排序政策、状态和诊断。每个run receipt引用必须包含`run_id/run_receipt_id/run_content_fingerprint/supersedes_run_receipt_id/status`。结果的`all/current`选择完成后，再对关联run的完整收据链执行相同语义：`all`保存全部收据引用，`current`先调用`current_experiment_run()`再保存唯一叶节点；无论何种模式都先验证完整收据链。这样`ExperimentRuns`导出能证明自己打印的具体收据，不能只靠run ID猜测。零匹配是合法`empty`且`row_count=0`；损坏、歧义或证据缺失分别为`failed`、`ambiguous`或`unavailable`，不能都伪装成空结果。推荐稳定排序键为合同固定顺序、instrument空值后置、signal date空值后置、窗口空值后置、`as_of`、`logical_result_id`、稳定结果ID。

### 10.3 ExportManifest与原子发布

`export_id`只由`QueryResultSet`身份／内容指纹和规范化`ExportConfig`决定；绝对输出路径与`generated_at`不进入该逻辑身份。每次实际物化另有`export_receipt_id`，由唯一共享函数对完整Manifest物化语义重算：包括逻辑`export_id`、实际`generated_at`、`code_commit`、M10-D来源版本、导出格式／编码／渲染政策、XLSX生成器与锁定依赖证据，以及规范排序后每个最终文件／part的路径、行数、字节数和SHA-256。只排除`export_receipt_id`自身及随后据完整Manifest计算的`manifest_content_fingerprint`，以避免自引用；验证不得信任调用方传入的收据ID。因此相同来源与配置即使代码提交不同仍有相同`export_id`，但不同物化语义必有不同`export_receipt_id`。`ExportManifest 2.0.0`至少保存：

- `export_id`、`export_receipt_id`、manifest内容指纹、export schema／source／config版本和配置指纹；
- 原始查询条件、`revision_mode`、库存ID／指纹、来源run ID集合；
- 来源结果ID／内容指纹全集及`source_result_set_fingerprint`；
- 合同、政策、日期、path／result／partition角色、bias与missing摘要；
- 请求格式、代码提交、`generated_at`及固定“非权威审核副本、不可回写”声明；
- 每个artifact的相对文件名、格式、part序号／总数、数据行数、工作表行数、首末稳定排序键、row-set指纹、字节数和实际文件SHA-256；
- 文件集合指纹、查询总行数及各part行数守恒证据。

Manifest本身不进入自己的artifact清单，避免自哈希循环。CSV／XLSX中不写实际生成时间；XLSX core properties的`created/modified`固定为渲染政策中的UTC常量，ZIP成员时间也由同一可复现政策控制，实际`generated_at`只写Manifest。所有文件只允许写入系统临时目录或仓库已忽略的`work/`；先在同文件系统的兄弟暂存目录逐个写完、关闭、重读核验行数／逐格规范值／SHA-256，再最后写Manifest并以`export_receipt_id`命名的原子目录重命名发布。任一步失败不得暴露半包或临时文件。目标已有完全相同Manifest和文件时幂等返回；相同receipt身份出现不同字节时冲突失败，不覆盖旧副本或人工修改副本。相同来源和配置必须保持同一逻辑`export_id`，固定渲染政策还必须使artifact字节SHA-256一致；不同实际生成时间只产生不同receipt证据。

### 10.4 CSV固定编码和列

M10-D1优先只用Python标准库`csv`：UTF-8无BOM、逗号分隔、RFC 4180引号和CRLF行结束；固定列顺序、固定行排序，不允许静默截断。序列化规则由`ExportConfig 1.0.0`绑定，并使用可逆、无碰撞的`audit_cell_codec_v1`：

- `null`唯一写为`\N`；任何真实文本若以反斜杠开头，先额外前置一个反斜杠，因此真实`\N`与null不碰撞；解码时精确单反斜杠`\N`还原为null，以双反斜杠开头的文本只去掉一个前缀反斜杠；
- 布尔固定为`true/false`，日期为ISO 8601，Decimal使用无指数的规范十进制字符串；
- 列表／对象使用键排序、无NaN／Infinity的规范JSON；
- ID、版本和指纹始终为文本，不允许电子表格转成科学计数法；
- 任意真实文本以ASCII单引号或`= + - @`开头时，额外前置一个ASCII单引号；解码时只对“双单引号”或“单引号＋危险字符”去掉一个前缀。这样原始`=x`编码为`'=x`、原始`'=x`编码为`''=x`，互不碰撞且都不能成为公式；
- 重读验证必须按上述逆规则恢复typed canonical值，任何非规范编码失败，不能只比较显示文本。

每种结果类型使用独立逻辑CSV数据集；超限时只按固定分片政策生成确定性part，全部part仍构成一份完整数据集：

| CSV | 固定列组 |
| --- | --- |
| `ForwardOutcomes` | 公共身份／版本／角色／修订列；event、instrument、signal date、行情／股票池／日历证据；窗口、target、entry、endpoint、gross／MFE／MAE及政策列。2.0的target只能为空，禁止推断 |
| `TradeOutcomes` | 公共列；event、plan、link、ExitState、行情／股票池证据；entry／exit、holding、gross、R、net状态、MFE／MAE状态及政策列 |
| `PortfolioStatus` | 公共列；验证后的TradeOutcome集合指纹、aggregation政策和portfolio scope；不得增加资本或表现字段 |
| `ResearchAggregates` | 公共列；来源类型／窗口／scope、来源集合指纹、状态计数、样本计数及已经冻结的M10-C毛收益统计；不得现场重算 |
| `ExperimentRuns` | run／receipt／前序身份、状态、证据窗口、角色、代码／配置／引擎、输入输出集合指纹、时间、错误和来源版本 |

一对多引用使用固定子表`PortfolioRunRefs`、`ResearchAggregateRefs`、`RunPolicyRefs`、`RunInputRefs`和`RunResultRefs`，每行保存父稳定ID、ordinal、引用角色、被引用ID和内容指纹；不得塞进不可查询的逗号字符串。所有主表公共列至少保留合同、schema/source版本、稳定结果ID、内容指纹、逻辑ID、前序ID、run ID、`as_of`、path／result／partition、status／reason、input fingerprint、bias labels和future-data标志。字段不适用与真实数值0必须可区分。

### 10.5 XLSX依赖、安全与精度

M10-D2已在独立研究导出依赖中精确锁定`XlsxWriter==3.2.9`，并在被忽略的`work/`隔离环境完成安装与哈希验证；它没有进入网站、Worker或生产依赖。官方PyPI元数据记录Python `>=3.8`、BSD-2-Clause许可证和2025-09-16发布；锁定文件为：

- wheel `xlsxwriter-3.2.9-py3-none-any.whl`，SHA-256 `9a5db42bc5dff014806c58a20b9eae7322a134abb6fce3c92c181bfb275ec5b3`；
- sdist `xlsxwriter-3.2.9.tar.gz`，SHA-256 `254b1c37a368c444eac6e2f867405cc9e461b0ed97a3233b2ac1e574efb4140c`。

权威来源为PyPI项目JSON、XlsxWriter官方文档及项目BSD-2-Clause LICENSE。该依赖只放入独立、精确锁定的本地研究导出依赖组，不进入网站或Worker环境；许可证证据只作技术记录，不构成法律结论。选用理由是它只生成、不读取或修改已有XLSX，并支持顺序行写入的`constant_memory`模式，正好强化单向审核副本边界。

设计证据链接：[PyPI 3.2.9 JSON](https://pypi.org/pypi/XlsxWriter/3.2.9/json)、[Workbook选项](https://xlsxwriter.readthedocs.io/workbook.html)、[constant_memory说明](https://xlsxwriter.readthedocs.io/working_with_memory.html)、[3.2.9版本归档的BSD-2-Clause LICENSE](https://raw.githubusercontent.com/jmcnamara/XlsxWriter/RELEASE_3.2.9/LICENSE.txt)及[Microsoft Excel规格上限](https://support.microsoft.com/en-us/office/excel-specifications-and-limits-1672b34d-7043-467e-8e27-269d656771c3)。

工作簿固定设置`constant_memory=True`、`strings_to_formulas=False`、`strings_to_urls=False`和`strings_to_numbers=False`，所有不可信文本使用安全的显式字符串写入；固定表名／列序、冻结首行、自动筛选、明确日期／数字格式、只读推荐属性，不含宏、外链或公式。收益、胜率、PF及其他指标只能写入M10已有值，禁止Excel公式重算。

Excel二进制数值不能冒充完整Decimal精度。首版渲染政策固定为：每个定点事实保留规范Decimal文本审计列；仅当数值能在Excel 15位有效数字限制内往返一致时，才另写可排序的展示数值列。CSV和XLSX从同一条唯一链路生成：已验证payload先生成全部主表和引用子表的canonical row projection，再生成CSV和XLSX；包复核重新解析并验证payload、重建相同投影，并精确比较表头、列序、行序和每个解码单元格，任何未知／缺失／重复列或子表行均失败。

D3使用Python标准库`zipfile`与`xml.etree.ElementTree`实现命名空间感知的只读OOXML严格子集校验器。它只接受本生成器固定的ZIP成员、content types、关系、工作表结构、单元格类型和XlsxWriter 3.2.9样式集合；拒绝单元格公式、任意defined name、data validation／conditional formatting／table计算公式、calc chain、external link、connection、DDE／OLE、宏／VBA、未知关系或异常成员。XlsxWriter正常生成的筛选器内建defined name只按精确sheet及范围白名单接受。固定style角色区分表头、文本／ID／SHA／日期、整数、布尔和Decimal；自定义数字格式只允许`@`及固定十位Decimal，`;;;`、`;;;@@@@@@@@`或任何额外样式即使未被单元格引用也失败。该校验器不读取或修改任意第三方工作簿，也不是第二业务计算入口；展示格式不参与权威身份。列宽、分页及打印页数不属于本修复。该精度政策已随D2批准并冻结。

### 10.6 工作表、拆分和人工审核

首版工作簿只为真实来源生成以下表：

1. `Run Summary`
2. `Forward Outcomes`
3. `Trade Outcomes`
4. `Research Aggregates`
5. `Portfolio Status`
6. `Bias & Missing Data`
7. `Version Evidence`
8. `Human Review`

结果类型没有来源行时不生成对应结果表，并在`Run Summary`的Coverage区明确`no_source_rows`。`Score Analysis`、`Factor Analysis`和`Pair Matrix`当前没有M10-C权威结果来源，因此不生成这些工作表；Coverage只标记`not_implemented`，不得生成看似有结论的空指标表。

`Run Summary`只显示查询与现有结果的总数、有效、missing、open、no_trade、pending、partial和unavailable，不计算新研究指标。`Version Evidence`保存模型、排行、事件、计划、评价、代码和数据的稳定引用；M10结果未直接保存的M07／M09细节只能在提供并重新验证对应不可变对象时展开，否则保留稳定引用并标记`unavailable`，不得猜造。每个结果行保留event ID、instrument ID、signal date、run ID、结果ID和内容指纹。

`Human Review`按来源结果生成稳定ID列和空白`reviewer/reviewed_at/decision/issue_type/notes/hypothesis`列，并醒目标明：表格修改不会回写机器账本，修改后原文件SHA-256失效；任何需要进入系统的观察必须通过M09／M11形成独立追加记录。M10-D不提供Excel导入器，Excel永远不能成为查询或后续计算输入。

Excel官方单表上限为1,048,576行；项目阈值固定为每表1,000,000条数据行，另保留一行表头。规范排序后按固定行数生成`Forward 001`、`Forward 002`等part；CSV与XLSX共同使用`partition_policy 1.0.0`。Manifest按逻辑dataset分别守恒：四类主结果表全部part的行数合计等于QueryResultSet相应合同的结果引用数，四类主结果合计等于全部结果引用数；`ExperimentRuns`等于`run_receipt_refs`数；每个引用子表等于对应来源对象实际引用数；Summary、Version、Bias和Human Review分别保存自己的期望行数。不得把所有不同表的行数错误地统一等同于查询结果数。任何dataset各part总行数、首末键或指纹不守恒即失败，任何单元格或文件无法无损表示时整次相应格式导出失败，不截断。工作簿采用顺序写入，不生成真实多年文件来测试拆分。

### 10.7 D1／D2／D3工作包

1. **M10-D1｜只读查询、库存证据、ExportManifest与CSV**：仅标准库；已建立唯一查询入口、`all/current`、确定性typed row set、可逆cell codec、`partition_policy 1.0.0`、原子导出与固定合成测试；分片阈值固定为1,000,000条数据行。
2. **M10-D2｜XLSX依赖闸门与单向生成器**：已按批准的精确pin、哈希、许可证和Decimal双表示安装隔离研究依赖；复用D1 row set、codec和分片政策生成XLSX，并固定所有可变工作簿元数据。
3. **M10-D3｜一致性与审核验收**：用标准库OOXML严格子集校验器重读CSV／XLSX逐格对账，验证确定性字节、分片、公式注入、文件SHA、人工修改失效和失败零半包。

每包目标不超过20分钟并形成独立审核点。M10-D不实现M10-E CLI，不接生产，不读取行情、不重算收益、不修改M09或任何M10结果，也不导入人工修改后的表格。

## 11. M12看板接口边界

M10未来只为M12提供小型、预计算、版本化的只读视图。页面不得运行回测或重算因子／收益。

- Apache ECharts候选用途：研究总览、分数单调性、因子表现、双因子热力图、分布、资金与回撤曲线；
- TradingView Lightweight Charts候选用途：K线、信号、入场、止损、目标、退出和forward节点，并保留适用归属说明；
- 现有Next.js／Vinext网站保持唯一正式前端；
- 不建立Streamlit、Dash或Jupyter第二套产品；
- M12按需加载图表依赖，不能因研究页面拖慢首页。

本轮不安装前端依赖，不设计页面，不创建看板JSON。

## 12. 旧数据只读兼容与迁移

- 每个旧文件只有一个明确legacy适配入口；适配器只读、不得回写或修改原字节。
- 旧ticker＋日期记录缺稳定上市身份时保持`ambiguous`或`unavailable`，不能与M09事件强行合并。
- 旧窗口、止损、费用或股票池证据缺失时，字段保持未知并附偏差，不得按新政策补算后冒充旧结果。
- 旧夜间断点继续按现行流程运行；M10设计和未来影子包均不移动断点、不修改已发布周或默认夜间入口。
- M12完成全链生产迁移、同源核验和回退批准前，旧网站和公开账本继续原样运行。

## 13. 验收矩阵

未来机械测试至少覆盖：

| 编号 | 反例／正例 | 必须结果 |
| --- | --- | --- |
| M10-01 | 信号日输入包含未来价格 | 失败关闭，不生成formal结果 |
| M10-02 | 1／5／20等窗口遇周末、假期、停牌 | 按交易日历和真实可用K线处理，不按自然日猜 |
| M10-03 | M08下一真实开盘尚未出现 | TradeOutcome保持`pending`，不猜价格 |
| M10-04 | 同日止损和目标同时触发 | 严格复用M08止损优先的已批准顺序 |
| M10-05 | 区间尚未成熟 | `pending`并保留旧版本，后续成熟只追加修订 |
| M10-05a | 窗口已经到期但停牌、退市或缺价 | `partial`或`unavailable`并保存明确证据，不猜价格 |
| M10-06 | 调整后价格口径或修订变化 | 保存M02政策与新身份，旧结果不覆盖 |
| M10-07 | 费用／滑点政策缺失 | formal毛收益可保存；formal净收益=`unavailable`，零成本净收益只能comparison |
| M10-08 | 空样本、无亏损、全零、非法非有限数 | 遵守第6.3节语义，JSON无NaN／Infinity |
| M10-09 | 当前股票池／ETF成员倒填过去 | formal失败；只能legacy偏差或`unavailable` |
| M10-10 | V2重算V1生效日前数据 | 只能comparison，不能覆盖权威V1 |
| M10-11 | development／validation／forward混用 | 身份验证失败 |
| M10-12 | 相同完整输入重放 | 相同ID、内容和结果 |
| M10-13 | 相同完整身份、不同内容 | 冲突失败，原结果不变 |
| M10-14 | 每日影子与回放使用相同输入和政策 | 逐股结果ID与内容一致 |
| M10-15 | ResearchAggregate尝试读取行情重算 | 拒绝；只接受不可变结果ID集合 |
| M10-16 | 未批准资本政策却请求组合曲线 | PortfolioRun=`unavailable` |
| M10-17 | 内部引擎与VectorBT固定样本 | 逐笔完全对账前VectorBT只能comparison |
| M10-18 | Excel与同一run的JSON | 数字、样本、版本和内容指纹一致 |
| M10-19 | 人工修改Excel | 不能回写或覆盖机器结果 |
| M10-20 | 旧失败／中断运行 | 收据永久保留且可从批准检查点继续 |
| M10-21 | ticker相同但上市身份不同 | 以instrument_id隔离，不猜测合并 |
| M10-22 | 输出出现评分／Gate／计划重算 | 范围测试失败 |

### 13.1 M10-C最小验收矩阵（已批准实施）

M10-C实施前必须以固定合成Outcome完成以下10项机械验收；本表是设计闸门，不表示测试或实现已经存在：

| 编号 | 固定正例／反例 | 必须结果 |
| --- | --- | --- |
| M10-C-01 | 同一完整输入集合以不同顺序交付；每日／回放未来调用同一输入 | 相同汇总ID、内容和数字；两个薄入口调用同一唯一生产器 |
| M10-C-02 | 重复结果ID、相同ID不同内容指纹，或同一`logical_result_id`的多个修订 | 失败关闭，不重复计数、不自动猜链尾 |
| M10-C-03 | Forward输入混合1／5／20／60／100日窗口 | 失败关闭；一份汇总只能绑定一个明确窗口 |
| M10-C-04 | 混合formal／legacy、authoritative／comparison、不同partition、结果类型或必要政策 | 失败关闭，不生成汇总 |
| M10-C-05 | Forward四状态（含有／无毛收益的partial）及Trade `completed/open/no_trade/unavailable`混合 | 逐项断言`total=sum(status_counts)=evaluated+missing`及`win+loss+flat=evaluated`；open与no_trade分别保留，只有真实有限gross_return进入收益分母 |
| M10-C-06 | 空输入，或输入存在但无可评价样本 | 收益统计为`null`且`metric_status=unavailable/metric_reason=empty_sample`；空输入`missing_rate=null`，非空全缺失为1 |
| M10-C-07 | 有盈利无亏损、无盈利有亏损、全部为0 | 分别得到`unbounded_no_losses`＋null、PF=0、`undefined_zero_profit_and_loss`＋null |
| M10-C-08 | 任一输入或派生数为NaN／Infinity | 验证失败，不落任何权威产物 |
| M10-C-09 | 向汇总器注入行情、bars／OHLCV或要求重算逐股收益 | 严格字段／函数边界拒绝；生产器只消费已验证Outcome |
| M10-C-10 | 资本政策未批准却请求Portfolio数字或曲线 | `PortfolioRun 2.1.0`只能`unavailable`且原因为`capital_allocation_policy_not_approved`，禁止任何资本或表现字段 |

### 13.2 M10-D最小设计验收矩阵（已批准实施）

以下14项冻结D1—D3的机械验收；批准设计不表示查询器、CSV或XLSX已经实现：

| 编号 | 固定正例／反例 | 必须结果 |
| --- | --- | --- |
| M10-D-01 | 按合同／版本／日期／instrument／事件／run／窗口／状态／政策查询；调换过滤数组顺序 | 精确匹配；同语义查询得到相同`query_id`，任一过滤语义变化得到不同ID；ticker歧义不猜测 |
| M10-D-02 | 对同一完整修订库存显式选择`all`或`current` | `all`保留全部历史；`current`先验全链再选唯一叶节点，旧pending不会因后续过滤复活 |
| M10-D-03 | 库存含坏ID／指纹、重复、未知版本、断链、分叉或循环 | 整次formal查询失败关闭，不静默漏行；旧2.x只按已知版本语义只读 |
| M10-D-04 | 调换源文件枚举顺序或Python哈希种子；对同一结果集和配置重复渲染 | 结果引用、稳定行排序、结果集指纹、分片、逻辑导出ID及artifact SHA-256不变 |
| M10-D-05 | CSV与XLSX读取同一typed row set | 由标准库重读后每个源ID／指纹、规范值、row-set指纹和行数完全一致 |
| M10-D-06 | null、空字符串、0、false及不适用字段并存 | 唯一编码且互不冒充；null绝不变成0 |
| M10-D-07 | 高精度Decimal和既有M10统计 | 规范文本保留原精度，展示列仅在可往返时为数值；没有Excel公式重算 |
| M10-D-08 | 文本以`= + - @`、单引号或反斜杠开头 | 可逆codec无碰撞；CSV与XLSX均为普通安全文本，不触发公式或URL；ID不变成科学计数法 |
| M10-D-09 | 固定小样本把每part阈值降至极小以触发拆分 | 无丢行、重复或静默截断；每个dataset的part总数／行数／首末键／指纹分别守恒 |
| M10-D-10 | 导出后人工修改XLSX任一单元格 | 文件SHA验证失败，不能回写、不能冒充原导出，也不能被同ID静默覆盖 |
| M10-D-11 | 正常、空结果和故意中断的导出 | Manifest逻辑export ID、物化receipt ID、来源全集、各dataset行数及artifact SHA正确；空结果明确0行；失败无公开半包 |
| M10-D-12 | 尝试向查询／导出注入行情、要求重算收益或新指标 | 严格边界拒绝；只读取和打印已验证不可变字段 |
| M10-D-13 | 请求写`public/`、生产目录或Git跟踪数据 | 路径闸门失败；只允许系统临时目录或已忽略`work/` |
| M10-D-14 | 用CSV／XLSX／可变current索引作为后续权威输入 | 失败关闭；权威仍是原M10 JSON、收据和修订链，不建立第二账本 |

## 14. 分阶段实施建议

每包保持小而可审核，核心与外部引擎分开批准：

1. **M10-A｜合同、身份和运行收据**：冻结四类2.x合同、`ExperimentRun 2.x`、角色／分区、幂等、冲突和失败收据；不算收益。
2. **M10-B｜内部Forward／Trade基线**：只用固定小样本实现逐股结果，复用M02／M08事实，验证防未来和执行顺序。
3. **M10-C｜Portfolio／Aggregate边界（里程碑已进入`main`）**：保留`PortfolioRun unavailable`守门，只读取单一类型Forward或Trade结果做最小gross汇总；资金政策未批准前不建资本曲线。
4. **M10-D｜准确查询、CSV／Excel审核副本（获批范围内`implemented`）**：D1查询／库存／Manifest／CSV、D2独立XLSX依赖闸门和D3一致性验收已完成独立审核并以纯fast-forward进入`main`；尚未部署或生产启用。
5. **M10-E｜配置和统一CLI（`implementing`）**：版本化JSON、非交互CLI、运行收据与显式断点设计已经批准，按E1／E2／E3实施；不接工作流。
6. **M10-X1｜VectorBT依赖及许可闸门**：独立批准最小依赖、锁定、哈希、安全和许可结论。
7. **M10-X2｜固定样本适配与逐笔parity**：同一数据集对照内部基线，结果只作comparison。
8. **M10-X3｜扩大comparison验证**：在用户另批样本范围内扩展，不触发真实多年生产回测。

M10-A—D已经完成审核并进入`main`。M10-D只生成可删除重建的审核副本，尚未运行真实历史导出或生成正式生产CSV／XLSX；M10-E已获批准并处于`implementing`，X1—X3仍未批准或开始。

## 15. 回退和生产边界

M10设计与未来影子实施默认不改现有生产入口，所以回退是停止调用并删除可再生成的影子`work/`产物；不可变证据和失败收据保留审计，不覆盖。

以下全部不属于本设计授权：

- 修改默认每日、夜间、回填或研究工作流；
- 改变M02—M09任何业务政策或身份；
- 运行真实多年回测、移动下一断点或改写历史结果；
- 安装VectorBT、Excel或图表依赖；
- 建立真实PortfolioRun资金政策；
- 生成生产Manifest、公开JSON、网站、Discord或部署；
- 把研究comparison升级为权威结果；
- 开始M11策略升级或M12生产接入。

旧规划中的大周期20／30日、小周期30→60→126日、100日敏感度、部分止盈、追踪退出和双退出家族均完整保留为`deferred_experiment`。本设计不删除这些想法，也不把它们写入首版Forward／Trade政策；以后必须分别预登记、使用独立样本验证并由用户批准。

## 16. 用户已批准的首轮选择

- `1A`：首版Forward窗口为`1／5／20／60／100`交易日。
- `2A`：费用／滑点政策未批准时，formal净收益为`unavailable`；零成本净收益只能是comparison。
- `3B`：连续实施A和B，但A必须先通过自身测试并形成独立提交；B完成后立即独立审核。
- 未成熟窗口为`pending`；到期后因停牌、退市或行情缺失才是`partial`或`unavailable`。
- formal TradeOutcome可保存毛收益，费用／滑点缺失只阻断净收益。
- 后续成熟结果只能追加不可变版本和修订链，不覆盖早期`pending`或M09事件。

M10-C已获得本节之外的独立明确实施授权；M10-D的D1／D2／D3已获得独立明确实施授权，XlsxWriter仅限隔离的研究导出依赖。M10-E的E1／E2／E3已获得独立明确实施授权并处于`implementing`；VectorBT X包、真实多年回测、生产接入、M11和M12仍未获批。

### 16.1 M10-A阶段里程碑（2026-09-02）

- M10-A已交付四类结果合同骨架、`ExperimentRun 2.x`、稳定身份与政策验证、formal／comparison／legacy隔离、不可变修订链和只追加影子存储。
- 提交链为设计`386ec4c`、首版合同`814112a`、首轮审核修复`3c79082`和最终合同收口`eb0399c97fb0b9deedea7cdc03735e58fb9b2063`；最终提交已通过独立审核并纯fast-forward进入`main`。
- M10-A没有计算真实`ForwardOutcome`或`TradeOutcome`；`PortfolioRun`和`ResearchAggregate`算法、M10-B、VectorBT、CSV／Excel、CLI和看板均未开始。
- 本里程碑不表示部署或生产启用。M10总体继续为`implementing`；M11和M12尚未开始。

### 16.2 M10-B审核与主线里程碑（2026-09-02）

- Forward基线提交`209d088045cd5c9d87be130a1c4b8499336cd202`只使用信号后下一有效交易日调整后开盘作为参考价格，并按注入的交易日序列形成1／5／20／60／100日结果；缺少下一开盘不回退其他价格。
- Trade基线提交`a81d97ce288f7b62224e08556145c93a41df4b5c`只读M08 TradePlan和完整ExitState链，计算毛收益与R收益；formal净收益在费用／滑点未批准时保持`unavailable`，首版Trade MFE／MAE保持`unavailable`并保存已冻结原因。
- 运行闭环提交`940604e8a004a2e2d0c54fbfeda1e7c6e8e3af65`要求先有pending `ExperimentRun 2.x`，结果完整验证后才追加complete收据；每日与回放薄入口调用同一评价器。
- 最终防未来与版本隔离提交`6ac5465ac3b2209dd3f2d0304125e4d6c7342569`删除未来`target_sessions`，按已发生session前缀建立1／5／20／60／100目标，并将新formal ForwardOutcome升级为严格`2.1.0`；旧`2.0.0`仅保留原字段只读兼容。
- 最终验收为：机械版本攻击及四闸门11项、M10合同与基线专项78项、M08与M10专项93项、M01—M10扩大定向274项、完整Python 630项、四种固定哈希种子每轮93项、治理19项及前端11项通过；Python编译、lint、TypeScript、生产构建、文档链接和差异格式检查通过。
- 最终审核确认：不存在未来session或target；20／60／100日成熟边界正确；ForwardOutcome 2.0.0／2.1.0严格隔离；5日`2026-09-09`改签为`2026-09-08`并重建身份仍失败；新formal pending、全部Outcome和completed共同使用`m10-b-internal-1.1.0`，公共存储无版本旁路，旧1.0历史只读，completed必须承接实际落盘pending链尾。
- M10-B审核通过代码HEAD为`108a29271c75ba6b49f1172350fc3adbf3460a25`，已以纯fast-forward方式进入`main`。进入主线不表示部署或生产启用；默认每日、夜间、网站、Discord和公开JSON没有切换，未访问EODHD或运行真实行情／真实历史回测。截至该里程碑，PortfolioRun、ResearchAggregate、VectorBT、CSV／Excel、CLI、看板、M10-C—E、M11和M12均未开始。

### 16.3 M10-C最小设计与实施批准（2026-09-03）

- 唯一职责：在不批准资本政策的前提下关闭Portfolio伪精确入口，并对已经冻结、口径一致的Forward或Trade gross结果做最小只读汇总；不读取行情、不重算逐股结果。
- 合同冻结：保留`PortfolioRun 2.0.0`和`ResearchAggregate 2.0.0`原语义只读；新formal M10-C分别使用严格字段隔离的`2.1.0`，来源版本固定为`m10-c-readonly-1.0.0`，汇总公式由唯一`aggregation 1.0.0`政策集中冻结。
- 唯一生产边界继续位于`services/evaluation/`；Portfolio边界、只读汇总、合同验证、运行收据、修订链和影子存储复用现有体系，不建立第二个事实生产者。每日与回放未来只允许调用同一汇总纯函数。
- 用户批准的固定合成Outcome影子实施已完成：设计冻结`dbcdcf6`、唯一只读生产与合同／存储边界`041e6be`、固定样本回归`a08dd33`，审核代码HEAD为`7bb635617ddcfb06277d23269cca9fdfe4cadb8d`。该HEAD已通过独立审核并以纯fast-forward方式进入`main`；进入主线不表示部署或生产启用。
- 最终验收：M10-C专项27项、M10合同／基线／汇总105项、M08与M10 120项、指定含M09集合139项、M01—M10扩大定向290项、完整Python 657项、四种固定哈希种子每轮M10-C 27项、治理19项和前端11项通过；Python编译、lint、TypeScript、生产构建、文档链接和格式检查通过。独立窄复核确认Portfolio始终诚实`unavailable`，ResearchAggregate不读取行情或重算逐股收益，重签统计、状态伪装、错误`as_of`、failed收据和PF量化边界均失败关闭，Trade `open/no_trade`分别守恒，状态、样本和收益分类守恒。
- M10-D／E、Portfolio资本算法、VectorBT、CSV／Excel、CLI、查询API、真实多年回测、M11和M12均未开始；CR-043继续为`captured`。

### 16.4 M10-D审核与主线里程碑（2026-09-05）

- 设计于2026-09-04获用户批准实施：唯一只读查询入口复用现有合同验证、完整修订链和`EvaluationShadowStore`，显式区分`all/current`，并以原子库存指纹证明查询看到的精确集合。
- 正式合同为`EvaluationQuery 2.0.0`、`QueryResultSet 2.0.0`、`ExportConfig 1.0.0`和`ExportManifest 2.0.0`，来源版本固定为`m10-d-query-export-1.0.0`。它们只记录查询与导出证据，不创建收益事实或第二权威账本。
- 提交链为设计`b90c269`、D1原子查询／Manifest／CSV`e7c649f`、D2锁定XLSX审核副本`ee6d596`、D3逐格一致／安全复核`d682897`和审核修复`61de04e`；审核通过代码HEAD为`f91a6fa5773561354b255f9217679f237b0f7017`，已以纯fast-forward方式进入`main`。`audit_cell_codec_v1`、1,000,000行分片、Decimal数值＋canonical text、标准库限定OOXML复核和Human Review只出不进均已机械验证。
- 首版工作表只覆盖已有Run、Forward、Trade、ResearchAggregate、Portfolio状态、bias／missing、版本证据和人工审核列。Score Analysis、Factor Analysis和Pair Matrix没有M10-C权威来源，不生成伪数据表。
- 最终独立审核确认原子库存和显式`all/current`、查询全集完备性、权威payload逐字段绑定、固定XLSX安全样式、命名空间感知OOXML安全复核、ExportManifest与导出身份、原子目录发布及Human Review只出不进均成立；五个审核闸门全部通过，原始六项完整重签攻击全部失败关闭。
- 最终验收：M10-D专项33项、M10 A—D 138项、完整Python 690项、四种固定`PYTHONHASHSEED`每轮33项、治理19项和前端11项通过；Python编译、独立依赖及许可证证据、lint、TypeScript、生产构建、43个本地文档链接和差异格式检查通过。
- M10-D只用固定合成样本在临时目录生成CSV／XLSX，没有读取行情、重算收益、提交生成文件、修改生产入口或接入网站／Discord。进入`main`不代表部署、生产启用或完成真实历史导出；Excel仍是人工审核副本，人工修改不能回写M10。M10-E现仅为`design_review`且CLI尚未实施；VectorBT、看板、真实多年回测、M11和M12仍未开始；CR-043继续为`captured`。
