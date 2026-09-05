# M11｜策略验证、批准与退休闸门最小设计

状态：`approved`

设计日期：2026-09-05

对应需求：`CR-2026-09-05-051`

## 1. 一句话职责

M11只把M09已经保存的人工假设和M10已经保存的不可变评价证据，整理成可追溯的候选、证据判断、用户决定、实现证明、生产激活和退休记录。

M11不计算收益，不读取行情，不改写旧事实，也不自行决定某个策略应该上线。

建议唯一中立实现层为`services/playbook/`。它只能消费稳定ID、内容指纹和已经通过上游验证的对象；不得从Excel文字、ticker或自由文本猜造证据。

## 2. 现场审计

### 2.1 已经存在的能力

- M09 `HumanReviewRecord`已经把`observation`、`hypothesis`和`approved_change`分开，并要求稳定`author_id`、时间、正文、证据引用和只追加修订。`approved_change`只表示批准意图，不表示验证、实现、部署或生产启用。
- M10已经提供`ForwardOutcome`、`TradeOutcome`、`PortfolioRun`、`ResearchAggregate`和`ExperimentRun 2.x`的稳定ID、内容指纹、版本、路径、角色、分区、数据、股票池、政策和代码提交证据。
- M10查询与审核导出可以准确找到已有结果；CSV/XLSX仍是只出不进的审核副本。
- `research/experiments.jsonl`当前有37条实验记录，`research/experiment-events.jsonl`有75条生命周期记录，其中26条事件标为完成；失败、样本不足、研究-only和前向观察仍被保留。
- `docs/rules/11_VALIDATED_PLAYBOOK.md`诚实记录当前没有正式验证策略；`docs/rules/12_HARD_RULES.md`已经保存系统完整性硬规则并说明单个案例不能直接成为交易红线。

### 2.2 当前缺口

- 旧实验账字段和状态是历史自由格式，不能直接证明满足同一套M11证据闸门。
- 仓库没有统一的M11合同、状态机、稳定策略版本身份或线性退休链。
- 规则11/12目前主要是人工模板，尚不能机械证明候选版本、基线版本、预登记标准、分区、偏差、审批、实现和生产激活彼此一致。
- M09人工记录和M10机器结果之间尚无唯一、可验证的晋级决策层。
- 当前没有代码自动修改生产规则，这是正确边界；M11设计不得引入这种旁路。

因此，现有研究结论全部保持原状态；本设计不把任何旧记录补标为`validated`。

## 3. 当前机器事实

- 生产最新完整美股收盘仍为2026-08-28。
- 夜间已保存历史覆盖2025-12-29至2026-08-28，共168个交易日；下一断点为2025-12-22至2025-12-28。
- M00—M10已在各自获批影子范围进入`main`；M03—M10尚未部署或生产启用。
- 当前正式验证策略数量为0；规则11继续显示“暂无”。
- M11、M12和M13尚未实施。CR-043继续为`captured`。

## 4. 人机证据链

唯一允许的追加链为：

```text
机器点时事实
→ 机器当时结论
→ 后续客观Outcome／Aggregate
→ 人工observation
→ 人工hypothesis
→ StrategyProposal
→ 预登记标准
→ ExperimentRun与结果证据
→ StrategyEvidenceAssessment
→ 用户决定
→ 进入main的实现证明
→ M12生产激活证明
→ 退休证明
```

每一层只能引用前层，不得覆盖或倒填。Excel批注必须先成为新的M09人工记录；M11不得直接读Excel或把表格文字当批准。

## 5. 四条独立状态轴

| 状态轴 | 允许值 | 唯一事实来源 |
| --- | --- | --- |
| 机器证据 | `candidate` / `evidence_incomplete` / `not_validated` / `validated` / `invalidated` | `StrategyEvidenceAssessment` |
| 用户决定 | `not_requested` / `approved_for_implementation` / `rejected` / `deferred` | 带稳定作者与批准引用的`StrategyLifecycleEvent` |
| 实现 | `not_implemented` / `implemented_in_main` | 代码提交、规则版本和测试证据对应的生命周期事件 |
| 生产 | `inactive` / `active` / `retired` | M12激活或退休证明对应的生命周期事件 |

四轴不得压成一个`status`：

- `validated`不等于用户批准；
- 用户批准不等于已经实现；
- 进入`main`不等于生产启用；
- M12激活前必须保持`inactive`；
- `retired`不删除历史证据，也不把旧事件改写为从未生效。

用户可以批准继续研究或批准实现某个候选，但这只能改变用户决定轴；证据不足时机器证据轴仍保持`evidence_incomplete`或`not_validated`，且不得进入`active`。

## 6. 最小合同

首版建议使用四个合同。前三个是不可合并的权威事实，第四个只是可再生成视图。

### 6.1 `StrategyProposal 2.0.0`

保存“究竟要改变什么”，不保存结果判断。

最小字段：

- `proposal_id`、`proposal_content_fingerprint`；
- 稳定`strategy_id`、严格SemVer `strategy_version`；
- `proposal_kind`：`playbook_candidate`或`alpha_risk_hard_rule_candidate`；
- 精确候选版本、基线版本、作用模块、政策范围、适用股票池／市场／周期和机器可执行定义；
- M09 `hypothesis`／`approved_change`引用及内容指纹；
- 已见案例引用和每个案例角色；
- 预登记引用及内容指纹；
- `created_by`、`created_at`、`as_of`、来源版本和bias标签。

相同策略版本只能有一个不可变提议身份。改定义、阈值、范围、基线或预登记均须新提议或新策略版本，不能改旧对象。

### 6.2 `StrategyEvidenceAssessment 2.0.0`

保存机器对证据门槛的判断，不计算任何M10指标。

最小字段：

- `assessment_id`、`logical_assessment_id`、内容指纹和直接前序；
- `proposal_id`、提议指纹、策略版本和证据闸门政策版本；
- 候选／基线版本与冻结预登记引用；
- 完成的`ExperimentRun`、Outcome、Aggregate和查询结果集合稳定引用；
- 数据、股票池、调整政策、代码提交、时间范围、formal／legacy、partition、成本／滑点、样本与缺失证据引用；
- 逐项预登记标准结果：`passed` / `failed` / `unavailable`，并保留实际证据引用；
- 案例角色及发现／验证隔离结果；
- `evidence_state`、原因、bias标签、评估日期和来源版本。

同一逻辑评估只能形成一条无分叉修订链；新窗口成熟或新增独立证据只追加新评估，不覆盖旧`evidence_incomplete`、失败或负结果。

### 6.3 `StrategyLifecycleEvent 2.0.0`

保存证据判断之外的人工决定、实现、激活和退休事实。

最小字段：

- `lifecycle_event_id`、内容指纹、`proposal_id`、策略版本；
- `event_type`：`proposal_registered`、`evidence_assessed`、`user_decision_recorded`、`implementation_recorded`、`production_activation_recorded`或`retirement_recorded`；
- 被改变的状态轴、旧值、新值、直接前序事件；
- 证据评估、批准、代码提交、规则版本、测试、M12 Manifest／部署／线上核验或退休依据的稳定引用；
- `author_id`、`occurred_at`、原因和bias标签。

每个提议版本只有一条线性生命周期。断链、分叉、循环、跨提议、跨策略版本、倒序和跳过直接前序均失败关闭。

### 6.4 `StrategyRegistrySnapshot 2.0.0`

这是可选但推荐的只读派生视图，用于回答“现在有哪些候选、已验证、已批准、已实现、active或retired策略”。它只能从前三类完整不可变记录重新推导：

- 保存输入记录ID／指纹全集、集合指纹、生成日期和代码提交；
- 每个策略版本显示四条独立状态轴；
- 输入顺序不改变身份或排序；
- 不产生新决定，不作为M12激活证明；
- 损坏、缺失、分叉或未知版本时失败关闭。

## 7. 证据验证闸门

M11不创造统一收益阈值。每个候选必须在看验证结果前，通过不可变预登记明确成功标准；M11只机械核对是否有完整证据以及每项标准的结果。

只有同时满足以下条件，机器证据轴才可为`validated`：

1. 候选和基线的精确策略、Gate、因子、模型、评分、排行、交易、退出和评价版本已经冻结；
2. 预登记ID、内容指纹、主指标、阈值、样本门槛、分区、成本／滑点、缺失处理和判定规则完整；
3. 引用的M10 `ExperimentRun`已经`completed`，收据链和结果全集合法；
4. 代码提交、配置、数据、股票池、复权、成员／退市覆盖和时间范围有稳定身份；
5. formal／legacy／comparison明确隔离，所有bias标签完整；
6. `development`、`calibration`、`validation`、`forward`和`explanation_only`角色不混用；至少有一个未参与定义或调参的独立`validation`或真实`forward`分区，且预登记要求的全部分区均已完成；
7. 样本量、缺失率、费用、滑点及M10不可用边界都有明确证据，缺成本时不得用毛收益冒充净收益标准；
8. 所有要求的Outcome／Aggregate、负结果、不利时期和失败案例均被引用，没有选择性删减；
9. 每项预登记标准均有明确`passed`，任何`failed`使结论为`not_validated`或`invalidated`，任何必要项`unavailable`使结论为`evidence_incomplete`；
10. 所有数字有限，NaN／Infinity和调用者自报但无法复核的指标失败关闭。

用户不能把缺失或失败证据重标为`validated`。人工决定可以批准继续研究或实现候选，但不能修改机器证据状态。

## 8. 案例角色与防止自证

每个案例必须且只能在当前提议中承担一个角色：

- `discovery`：发现问题或机会；
- `calibration`：帮助冻结定义或阈值；
- `validation`：定义冻结后才接触的独立检验；
- `forward`：冻结并启用观察后真正新发生的事件；
- `explanation_only`：只帮助人工理解，不参与有效性结论。

规则：

- `discovery`和`calibration`永远不能在同一提议版本中改标为`validation`；
- 已经看过的CGEM、MRNA、BTDR、DLTR、ADBE、BABA、TTD和AEVA只能保留其真实发现、校准、风险回归或解释角色；
- 修改规则以匹配某案例后，该案例不能再证明规则有效；
- 同一`event_id`不得跨角色重复计入样本；
- 无法确认角色时为`evidence_incomplete`，不能猜测；
- 人工选出的赢家、输家和边界案例必须保留，不能只保留支持候选的案例。

## 9. 用户批准、实现和生产激活边界

### 用户决定

- 必须引用稳定、非空`author_id`、时间、正文、提议版本和证据评估；
- `approved_for_implementation`只是批准实现意图；
- `rejected`和`deferred`永久保留，后续改变决定必须追加新事件；
- M09旧`approved_change`可以成为提议来源，但不能代替M11用户决定事件。

### 实现证明

`implemented_in_main`至少绑定精确规则版本、完整40位代码提交、测试证据和提议版本。它不改变历史提议、实验或评价，也不代表部署。

### 生产激活

只有下列条件全部成立，M12才能追加`active`事件：

- 机器证据为`validated`；
- 用户决定为`approved_for_implementation`；
- 实现为`implemented_in_main`；
- M12提供精确生产Manifest、部署提交、线上核验和生效日期；
- 激活的策略版本和适用范围与提议完全一致。

M11本身不得写生产Manifest、切换工作流、修改网站／Discord或把`inactive`改为`active`。

## 10. Playbook与Hard Rules边界

### 已验证策略宝典

规则11只展示满足证据闸门的策略版本。`validated`但未批准、未实现或未激活的版本必须显示各自四轴，不能写成“正在生产使用”。当前仍为0条。

### 系统完整性硬规则

防未来、不可覆盖、数据缺失失败关闭、风险纪律等系统完整性规则保护研究和执行正确性，不是交易alpha，不要求用收益样本证明。修改它们仍需治理批准、实现证据；若影响生产，还需M12激活证明。

### 交易alpha／风险红线

任何形态、因子、市场条件或退出条件要成为交易红线，必须走完整M11证据闸门，并另外保存：

- 可执行禁止条件；
- 适用范围和例外；
- 解除／退休条件；
- 精确候选与基线版本；
- 用户批准、实现和M12激活证明。

单个亏损、单个赢家、高分或人工直觉都只能产生候选，不能直接成为active红线。

## 11. 版本、修订和退休

- 合同使用严格允许字段、SemVer和内容寻址ID；未知主版本失败关闭。
- 同一完整身份、相同内容重放幂等；相同身份、不同内容冲突失败。
- V1、V2及以后版本永久并存，旧提议、旧评估、旧批准、旧实现和旧生产事件不得覆盖。
- 证据成熟使用评估修订链；定义变化使用新策略版本，不能伪装成原版本证据成熟。
- 生命周期每次只追加一个直接后继；并发写入最多一个成功。
- `retired`必须保存停用生效日、原因、替代版本（如有）、批准者和M12停用证明；不删除此前`active`记录。
- 已退休版本不得重新变回`active`；恢复使用必须建立新策略版本和新提议。

## 12. 验收矩阵

1. M09 `hypothesis`可建立候选，但`observation`、Excel文字或裸ticker不能直接晋级。
2. 缺预登记、完成运行、独立分区、数据／股票池、成本或必要指标时只能`evidence_incomplete`。
3. 任何失败标准、负结果和不利时期不能删去；选择性引用失败关闭。
4. discovery／calibration案例混入validation失败，已见八个固定案例保持非独立角色。
5. 用户批准不能把`not_validated`或`evidence_incomplete`改成`validated`。
6. `validated`、`approved_for_implementation`、`implemented_in_main`和`active`四轴可独立表达且不可互相冒充。
7. 缺M12 Manifest／部署／线上核验时，即使前三轴满足也必须保持`inactive`。
8. 定义或范围改变必须产生新策略版本；V1证据与V2证据不能混用或覆盖。
9. 相同记录幂等；同身份不同内容、断链、分叉、循环、跨提议或跨版本修订失败。
10. 退休只追加且保留完整active历史；退休版本不能原地复活。
11. Playbook条目与交易alpha硬规则都可追溯提议、评估、批准、实现和激活证据；系统完整性规则明确使用不同证明路径。
12. 派生RegistrySnapshot输入顺序不影响身份；坏记录或缺记录不产生“当前active”视图。
13. M11实现测试只使用合成稳定引用，不读取行情、不运行回测、不计算新指标。
14. 当前仓库必须继续得到0个formal validated策略、0个新增交易alpha硬规则和0个生产激活。

## 13. 快速实施包（已批准）

- A（≤20分钟）：四类合同骨架、严格字段、状态轴、稳定身份、内容指纹和公共验证入口。
- B（≤20分钟）：证据闸门、预登记标准核对、案例角色与分区隔离、缺失和bias失败关闭。
- C（≤20分钟）：用户决定、实现证明、M12激活引用、退休事件及线性不可变存储。
- D（≤20分钟）：只读RegistrySnapshot、固定合成样本、每日／回放未来同源接点和验收证据。

每包完成自身专项测试后才进入下一包。超过批准边界、出现语义冲突或需要生产权限时停止。

## 14. 明确不做

本设计和未来M11首包均不得：

- 读取M02行情、运行真实回测或计算Forward／Trade／Portfolio／Aggregate；
- 重新计算Gate、因子、模型、评分、排行、计划、退出或统计；
- 自动搜索参数、挑选阈值或创造统一收益标准；
- 把M09人工记录、Excel批注或旧自由格式实验账直接升级为验证结论；
- 修改M03—M10旧事实、旧版本、旧结果或生产断点；
- 自动改代码、规则文件、评分、权重、交易政策或生产配置；
- 创建网站、看板、Discord、查询API、CSV/XLSX导入或公开JSON；
- 部署、激活生产、发送Discord或提前实施M12／M13；
- 接入VectorBT或启动M10-X扩展。

## 15. 已批准选择

1. `1A`：采用上述四合同方案，`StrategyRegistrySnapshot`仅作可再生成的只读派生视图。
2. `2A`：`validated`至少需要一个未参与定义／调参的独立`validation`或真实`forward`分区，并满足预登记声明的全部必需分区和通过标准。
3. `3A`：用户可在证据尚未`validated`时批准候选实现，但只改变用户决定轴，不改变机器证据、不自动改规则或代码、不激活生产；生产仍须`validated`＋批准＋main实现＋M12证明四者齐全。

用户已批准A—D影子实施；任何新业务选择、真实策略晋级或范围扩张仍须停止并重新评审。
