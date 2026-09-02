# M10｜统一评价、回测与外部研究引擎设计

- 文档状态：M10-A合同里程碑已进入`main`；M10-B已在审核分支完成本地验收；M10整体仍为`implementing`
- 对应需求：`CR-2026-09-02-050`
- 基线提交：`5dfd0a57fc1dad56042c0db6b8e2c3ce9ff88251`
- 设计日期：2026-09-02
- 生产状态：M10-A影子合同基础已进入`main`；M10-B仅为待独立审核的影子实现；未部署、未生产启用

> 本文冻结M10的职责、合同边界、身份和失败关闭语义。M10-A已经完成审核并进入`main`；M10-B已按批准口径完成固定样本实现和本地验收，尚待独立审核与合并。C—E、VectorBT、真实多年回测、生产目录、M11和M12仍未批准。

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

最小字段：

- `portfolio_run_id`、组成它的不可变TradeOutcome ID／指纹集合；
- 组合政策版本、初始资本、仓位分配、最大同时持仓；
- 资金不足时的确定性信号处理规则；
- 基准身份、费用／滑点政策；
- 每个交易日的现金、持仓、市值、已实现／未实现权益；
- 总收益、年化、最大回撤及数据完整性；
- 被拒绝／延迟信号和原因。

当前没有获批资金分配和资本竞争政策，因此正式`PortfolioRun`必须为`unavailable`。任何旧脚本的非重叠cohort或独立逐股收益拼接只能标记为研究诊断，不能冒充资本受限组合曲线。

### 5.4 ResearchAggregate 2.x

回答：“一组已经冻结的逐股或组合结果呈现什么统计规律？”

它只读取前三类不可变结果及其稳定引用，绝不重新读取行情计算另一套价格结果。最小字段：

- `research_aggregate_id`、`experiment_id`、`run_id`；
- 精确输入结果ID和集合指纹；
- 查询、过滤、分组和统计政策版本；
- 样本总数、有效数、缺失数／率及排除原因；
- 胜率、平均／中位收益、Profit Factor、expectancy；
- 分数单调性、单因子lift和双因子矩阵；
- development／validation／forward分区结果与稳定性；
- 偏差、不可重建区间及内容指纹。

分数、因子和上下文标签只能来自M07／M09冻结引用。ResearchAggregate不能反向修改逐股结果，不能用新的行情重算后保留旧ID。

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

JSON不得写`NaN`、`Infinity`或`-Infinity`。建议冻结以下机械语义：

| 情况 | `profit_factor` | 状态说明 |
| --- | --- | --- |
| 没有可评价样本 | `null` | `unavailable: empty_sample` |
| 有正收益且总亏损绝对值为0 | `null` | `unbounded: no_losses`，不能写Infinity |
| 没有正收益但存在亏损 | `0.0` | 有限、可解释的零 |
| 全部结果恰为0 | `null` | `undefined: zero_gross_profit_and_loss` |
| 输入包含非法非有限数 | 无结果 | 验证失败，不落权威产物 |

胜率、平均值、年化等指标同样必须定义空样本、分母和最小样本要求；没有证据时写`null + reason`，不得用0掩盖缺失。

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

未来首版使用Git版本化、不可原地修改的JSON配置，以及非交互式入口：

```text
python3 -m research.run --config research/configs/rsi-support-v1.json
```

配置最少包含：

- `config_id`、`schema_version`、内容SHA-256；
- `research_type`；
- 因子或因子对引用；
- universe、行情和复权政策；
- 日期范围及development／validation／forward分区；
- ForwardOutcome窗口政策；
- TradePlan、执行、费用和滑点政策；
- 引擎及适配器版本；
- 输出合同／格式版本。

运行过程不得修改配置。CLI不得靠提示输入隐藏未保存选择，也不得从“最新政策”自动推断版本。未来M12网页表单只能生成并提交同一配置，不能维护另一套研究逻辑。

## 10. 存储、查询与导出

| 内容 | 未来位置／形式 | 权威性 |
| --- | --- | --- |
| 运行收据、逐股结果、汇总 | 只追加JSON／JSONL及run manifest | 权威机器证据 |
| 研究配置 | Git版本化JSON | 权威可复现输入 |
| 大型可再生成中间缓存 | `work/`或系统临时目录 | 非权威，可删除重建 |
| CSV／Excel | 从权威结果按export config生成 | 审核副本，不是账本 |
| M12看板数据 | 预计算的小型只读JSON | 可再生成视图 |
| `public/` | 本轮禁止写入 | 生产集成留给M12 |

查询层必须按稳定ID、策略／政策版本、日期、instrument、事件、运行、窗口、状态、路径、角色和分区过滤；不能靠文件名中的ticker和日期猜身份。

### 10.1 CSV／Excel边界

Excel至少规划以下工作表：

- `Run Summary`
- `Trade Outcomes`
- `Forward Outcomes`
- `Score Analysis`
- `Factor Analysis`
- `Pair Matrix`
- `Bias & Missing Data`
- `Version Evidence`

每份导出至少保存导出ID、来源run ID、策略及各政策版本、日期范围、formal／legacy、股票池与退市覆盖、数据修订、代码提交、配置指纹、样本与缺失、费用／滑点、窗口／持仓规则、源结果集合指纹、内容SHA-256、生成时间，以及“人工修改后不再是权威结果”的说明。

导出器只读权威结果。Excel人工批注若未来需要回系统，必须走M09／M11独立追加流程，不能回写M10结果。具体列、拆分、大小限制和Excel依赖在实施D包前再次确认。

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

## 14. 分阶段实施建议

每包保持小而可审核，核心与外部引擎分开批准：

1. **M10-A｜合同、身份和运行收据**：冻结四类2.x合同、`ExperimentRun 2.x`、角色／分区、幂等、冲突和失败收据；不算收益。
2. **M10-B｜内部Forward／Trade基线**：只用固定小样本实现逐股结果，复用M02／M08事实，验证防未来和执行顺序。
3. **M10-C｜Portfolio／Aggregate边界**：先实现`PortfolioRun unavailable`守门和只读汇总；资金政策未批准前不建资本曲线。
4. **M10-D｜存储、查询、CSV／Excel**：只追加存储、查询和可再生成导出；Excel依赖及格式另行确认。
5. **M10-E｜配置和统一CLI**：版本化JSON、非交互CLI、运行收据与断点；不接工作流。
6. **M10-X1｜VectorBT依赖及许可闸门**：独立批准最小依赖、锁定、哈希、安全和许可结论。
7. **M10-X2｜固定样本适配与逐笔parity**：同一数据集对照内部基线，结果只作comparison。
8. **M10-X3｜扩大comparison验证**：在用户另批样本范围内扩展，不触发真实多年生产回测。

本轮只批准A—B连续实施，并要求A测试通过、独立提交后才能进入B。B完成后立即做快速独立审核；C—E和X1—X3均未批准。

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

C—E、VectorBT X包、真实多年回测、生产接入、M11和M12不随上述选择获批。

### 16.1 M10-A阶段里程碑（2026-09-02）

- M10-A已交付四类结果合同骨架、`ExperimentRun 2.x`、稳定身份与政策验证、formal／comparison／legacy隔离、不可变修订链和只追加影子存储。
- 提交链为设计`386ec4c`、首版合同`814112a`、首轮审核修复`3c79082`和最终合同收口`eb0399c97fb0b9deedea7cdc03735e58fb9b2063`；最终提交已通过独立审核并纯fast-forward进入`main`。
- M10-A没有计算真实`ForwardOutcome`或`TradeOutcome`；`PortfolioRun`和`ResearchAggregate`算法、M10-B、VectorBT、CSV／Excel、CLI和看板均未开始。
- 本里程碑不表示部署或生产启用。M10总体继续为`implementing`；M11和M12尚未开始。

### 16.2 M10-B本地验收里程碑（2026-09-02）

- Forward基线提交`209d088045cd5c9d87be130a1c4b8499336cd202`只使用信号后下一有效交易日调整后开盘作为参考价格，并按注入的交易日序列形成1／5／20／60／100日结果；缺少下一开盘不回退其他价格。
- Trade基线提交`a81d97ce288f7b62224e08556145c93a41df4b5c`只读M08 TradePlan和完整ExitState链，计算毛收益与R收益；formal净收益在费用／滑点未批准时保持`unavailable`，首版Trade MFE／MAE保持`unavailable`并保存已冻结原因。
- 运行闭环提交`940604e8a004a2e2d0c54fbfeda1e7c6e8e3af65`要求先有pending `ExperimentRun 2.x`，结果完整验证后才追加complete收据；每日与回放薄入口调用同一评价器。
- 本地验收为：M10-A／B专项57项、M01—M10扩大定向251项、完整Python 607项、四种固定哈希种子每轮57项、治理19项及前端11项通过；Python编译、lint、TypeScript、生产构建和差异格式检查通过。
- M10-B当前只达到审核分支`verified`，不表示已经合并、部署或生产启用。没有运行真实多年回测，没有实现PortfolioRun、ResearchAggregate、VectorBT、CSV／Excel、CLI、看板、M11或M12。
