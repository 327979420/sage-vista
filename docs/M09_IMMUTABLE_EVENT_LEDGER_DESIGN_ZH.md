# M09｜一本不可变事件总账与追加式人工审核设计

- 关联需求：`CR-2026-09-01-049`、跨模块诉求`CR-2026-09-01-043`
- 状态：`implementing`（用户已批准`1A/2A/3A`及A—E连续影子实施）
- 基线：`a4ce610f4addd28fca444f28ba38298e4a64199d`
- 边界：本文件是设计，不等于实施、验证、合并、部署或生产启用

## 人话版

M09像一本不能用橡皮擦的病例本。股票某天正式入榜，就建立一页唯一事件；以后换评分版本、掉榜、亏损、停牌或退市，这一页仍然存在。

机器当时看到的证据只允许引用和追加，不能改写。用户可以在旁边追加“我觉得这是误收”“这里可能有新形态”等批注，但批注不能变成机器原话，也不能自动升级成新规则。

M09不算后来赚了多少，不做MFE／MAE，不生成Excel，也不接网站或Discord。它只保证以后能准确找到“当时发生了什么”。

## 1. 当前链路与真实问题

当前有两套旧账和两个轻量视图：

| 当前产物 | 当前职责 | 已确认问题 |
| --- | --- | --- |
| `public/signal-history.json` | 69个生产前向case；每天原地推进生命周期和后续价格 | 首次机器快照有指纹，但生命周期、收益和MFE／MAE混在同一对象；没有稳定`instrument_id`和M03—M08身份 |
| `public/signal-history-summary.json` | 网站轻量视图 | 没有稳定case ID和内容身份，只是可再生成视图 |
| `public/opportunity-ledger.json` | 4,451个历史排行／生产case合并事件及评价 | 身份只有ticker＋日期；每次重建会重算收益，缺失上游事件可能消失；不是机械只追加 |
| `public/opportunity-ledger-latest.json` | 最近200条网站视图 | 是公开视图，不是权威账本 |

当前生产者分别是`services/scanner/signal_history.py`和`services/scanner/opportunity_ledger.py`。后者还直接计算收益、MFE、MAE和策略结果，这些属于M10，不得搬进M09。

旧账均缺少`instrument_id`、`universe_id`、`market_snapshot_id`、`gate_event_id`、证据ID、排行快照ID和完整政策身份。因此旧账只能作为legacy历史证据，不能仅凭ticker、日期或数量升级为formal事件。

## 2. 一句话职责与唯一负责人

> M09只把M07每个入榜记录冻结为唯一、不可变、可追溯的事件，并把后续机器引用和人工审核作为独立记录追加；不计算上游事实或下游表现。

唯一formal生产层建议为`services/ledger/`：

- 只有这里可以创建新的formal `event_id`、机器追加记录ID和人工审核ID。
- M03—M08只提供不可变输入；M09不得重算Gate、因子、模型、上下文、分数、排名、支撑、止损或退出。
- 每日影子与回放影子只调用同一M09纯生产器。
- 查询索引、摘要和未来网页JSON只是可再生成视图，不是第二本账。

目标链路：

```text
M07 RankingSnapshot 2.x
+ M03—M06不可变证据引用
→ 唯一OpportunityEvent 2.x
→ M08计划／退出引用只追加
→ HumanReview只追加
→ 未来M10结果引用（本轮不定义）
```

## 3. 事件创建边界

推荐冻结以下边界：

1. M07 `RankingSnapshot 2.x`中的每个`ranked_entries`条目恰好对应一个M09事件；`selected_entries`只决定M08是否尝试建计划，不决定事件是否存在。
2. `excluded_entries`不伪造OpportunityEvent。它们继续保存在M07不可变排行快照；人工漏检审核可以引用`ranking_snapshot_id + score_result_id`。
3. 只有`ranking_role=authoritative`才能生成`OpportunityEvent 2.x`。`shadow`和`comparison`继续由M07不可变快照保存，不建立事件根；固定样本可以在影子目录验证权威合同能力，但不得把比较重算冒充当时正式入榜。
4. 个人形态的M05判断只能挂在同一个事件下，不创建第二张主榜或第二个事件。
5. 同一稳定上市实体同一信号日最多一个事件根；次日再次入榜是新事件。ticker变化不改变同一`instrument_id`，重上市产生的新`instrument_id`不与旧实体混淆。
6. 整批任何必要引用缺失、错日、跨证券、跨Gate或内容指纹不符时失败关闭，不生成半本账。

## 4. 事件身份与不可变机器事实

`event_id`只绑定：

```text
schema_major=2
+ authority_scope=complex_multifactor_main
+ instrument_id
+ signal_date
```

不把ticker、当前排名、评分版本、行情快照或Gate证据版本放进根身份。原因是它们会修订或升级；把它们写进根身份会让同一股票同一天被复制成多个事件。

`OpportunityEvent 2.x`至少保存：

- `event_id`、`instrument_id`、信号日和当时ticker；
- `path_status`与`event_role`；
- `ranking_snapshot_id`、排行内容指纹、`score_result_id`、当时名次及是否精选；
- M03 `logical_signal_id`、当时精确`gate_event_id`及修订链引用；
- M04证据批次ID及排序稳定的`technical_evidence_ids`；
- M05批次ID及同一Gate下所有模型判断ID；
- M06批次ID及上下文ID；
- M07评分、排行和权威政策版本／指纹；
- M02 `universe_id`、`market_snapshot_id`及完整复权政策身份；
- `future_data_used=false`和事件内容指纹。

上游ID和内容指纹是权威引用。为便于人工查询，可以复制当时名次、精选标记、分项、警告和缺失项，但生产器必须逐项与M07快照核对；这些冻结副本不得成为第二套计算结果。

幂等与冲突：

- 相同输入重复运行得到相同`event_id`和内容。
- 相同`event_id`、相同内容是安全重放。
- 相同`event_id`、不同内容必须冲突失败，不能“以最新为准”。
- 行情、Gate或策略版本修订不得覆盖原事件；有明确上游修订证据时只能追加机器引用。

## 5. 后续机器引用

事件在入榜时立即创建，不能等下一交易日开盘后才记账。M08计划晚一天才可能形成，因此使用独立、不可变的机器追加记录：

- `trade_plan_decision`：绑定`trade_plan_batch_id + score_result_id`，保存`created`、`not_created`或`unavailable`及M08原始原因；
- `trade_plan`：计划存在时引用`plan_id`和内容指纹；
- `exit_state`：只引用M08不可变`exit_state_id`及其前一状态，不在M09重算退出；
- 未来M10的结果引用等M10设计时另行冻结，本轮不预设字段。

同一来源记录重复追加必须幂等；同一来源身份对应不同内容必须失败。任何追加都不能修改OpportunityEvent。

## 6. 人工审核

人工意见使用独立`HumanReviewRecord`，不得写入机器事件对象。最小字段：

- `review_id`；
- `subject_type=event|ranking_exclusion`；
- `event_id`，或M07排除项的`ranking_snapshot_id + score_result_id`；
- `review_type=observation|hypothesis|approved_change`；
- 调用者注入的稳定`author_id`；
- `authored_at`、文字说明、证据引用和标签；
- 可选`supersedes_review_id`，用于更正人工批注但保留原记录；
- `approved_change`必须带已有治理／M11批准引用。M09不能把普通观察自行升级成已批准规则。

同一内容、作者和时间重复提交得到同一ID。修改文字必须产生新记录；不得原地编辑旧记录。M09影子阶段不建设账号、权限UI或Excel回写，`author_id`只作为注入的审计标签。

## 7. 一本账的存储与查询

只建立一个`EventLedgerStore`。内部可以按记录类型分目录，但共同遵守同一验证、身份和只追加入口：

```text
work/m09-event-ledger-shadow/
  events/
  machine-links/
  human-reviews/
  legacy-audits/
```

- 只允许系统临时目录或仓库内部受保护的`work/`影子目录。
- 使用规范JSON、临时文件、完整验证和原子创建；已存在内容不得替换。
- 可再生成索引支持按日期范围、`instrument_id`、策略／政策版本、名次、精选状态、事件角色和人工类型查询。
- 结果状态、持仓窗口、收益区间和Excel查询留给M10；M09不伪造这些字段。
- 真实永久目录、Manifest、公开摘要、网站、Discord和工作流切换留给M12。

## 8. 旧两本账只读对账

四份旧JSON继续原样运行并保持字节不变。M09只建立两个只读适配入口和一份对账报告：

- 保存来源文件SHA-256、旧schema、数据日、记录数和原始ID；
- 分类为`matched_explicitly`、`opportunity_only`、`signal_only`、`ambiguous`或`conflict`；
- 只有真实显式来源ID才能认定匹配。当前Opportunity Ledger合并时会丢掉部分Signal History ID，单靠ticker＋日期只能标记`ambiguous`，不能猜合并；
- 不补造稳定证券ID、股票池、行情、Gate、证据、模型、排行或代码提交；
- legacy记录不得进入formal `OpportunityEvent 2.x`；
- 不删除或退休旧生成器。生产消费者全部迁移并经M12批准、部署和对账前，两套旧账继续运行。

## 9. formal、legacy与版本升级

- formal只接受`OpportunityEvent 2.x`及完整M03—M08引用。
- 旧`OpportunityEvent 1.x`和旧公开JSON只能显式legacy只读。
- 未知主版本失败关闭；同主版本新增可选字段可以兼容。
- 事件合同含义变化升级主版本；新增可选审计字段升级次版本；文字或不改变结构的修正升级补丁版本。
- 新版本不能改写旧事件或旧人工记录。
- `shadow`、`comparison`和`authoritative`必须在身份、路径和查询结果中明确，不能自动互相升级；前两者不得进入formal事件生产器。

## 10. 每日与回放同源

M03—M08已经为每日和回放提供同源影子链。M09只增加两个薄入口，把已生成的批次和记录交给同一个纯生产器：

```text
daily inputs ─┐
              ├→ produce_event_ledger_batch(...)
replay inputs ┘
```

两条入口不得读取旧公开账来补formal证据，不得重新计算上游业务事实，也不得写生产文件。

## 11. 明确不做

M09不做：

- 收益、R收益、MFE、MAE、胜率、PF或策略总体表现；
- 回测、前向评价、开发／验证／前向期划分；
- Excel生成、导入或人工批注回写；
- 修改Gate、因子、模型、上下文、评分、排行、计划或退出；
- 自动把人工意见变成规则；
- 删除、覆盖或正式迁移旧账；
- 修改默认每日／夜间入口、工作流、`public/`、网站或Discord；
- 生产Manifest、部署、真实回测、M10、M11或M12实施。

## 12. 机械验收矩阵

1. M07每个`ranked_entries`条目恰好创建或幂等复用一个事件，数量守恒。
2. M07排除项不伪造事件；人工漏检记录可以稳定引用该排除项。
3. 同一`instrument_id + signal_date`的复杂模型和个人形态判断只挂一个事件。
4. 同一输入、不同输入顺序和四种固定`PYTHONHASHSEED`产生相同身份与内容。
5. 相同事件身份不同内容失败关闭。
6. 次日再次入榜产生新事件；同ticker不同上市实体不能混淆。
7. `shadow`、`comparison`和`authoritative`严格隔离；comparison不能冒充当时权威事件。
8. 缺少、错日、跨证券或指纹不符的M03—M08引用让整批失败。
9. 入榜日立即建立事件；缺少下一开盘或计划不能删除或阻止事件。
10. M08计划决定、计划和退出状态只追加引用，不修改事件。
11. 事件掉榜、计划不可用或后续数据缺失时原事件字节不变。
12. 人工`observation`和`hypothesis`可以并存，均不改变机器事件。
13. 无批准引用的`approved_change`失败；合法记录仍不自动改变任何政策。
14. 人工更正通过`supersedes_review_id`新增记录，原批注保留。
15. 两份旧全量账适配前后字节和SHA-256完全不变。
16. 仅ticker＋日期的旧账重合标记为`ambiguous`，不得自动升级formal。
17. 每日与回放对相同输入得到相同事件批次身份。
18. 输出禁止出现收益、MFE、MAE、Excel、排名重算或交易重算字段。
19. 影子存储拒绝`public/`、`automation/`、仓库根和外部注入路径。
20. 默认生产入口、旧账、网站、Discord和工作流零变化。

## 13. 文件边界与回退

设计获批后的预计允许范围：

- `docs/rules/07_RANKING_AND_TRACKING.md`；
- `docs/CHANGE_REQUESTS_ZH.md`、`docs/DECISION_LOG_ZH.md`和本设计／验收文档；
- `services/contracts/`中M09合同衔接的最小修改；
- 新建`services/ledger/`；
- M09测试及每日／回放现有影子入口的最小连接。

明确禁止：生产工作流、`public/`、`automation/`、网站、Discord、真实缓存、旧账生成器、M10评价和Excel实现。

回退方式：M09只新增未接生产的影子入口。停用影子调用或删除未纳入生产的`work/`影子产物即可回退；旧账、旧页面和旧工作流继续原样运行。任何旧账字节变化、上游身份无法对齐或事件数量不守恒都立即停止。

## 14. 未来实施小包（均预计不超过20分钟）

1. 包A：更新规则，冻结M09合同、事件边界、人工追加和旧账只读语义。
2. 包B：实现`OpportunityEvent 2.x`唯一纯生产器、引用验证和批次守恒测试。
3. 包C：实现唯一只追加存储、M08机器引用、人工审核记录和最小查询。
4. 包D：实现两本旧账唯一只读适配／对账，以及每日／回放同源影子入口。
5. 包E：完整本地验收、独立审核材料、分开提交；不部署、不接生产。

## 15. 用户已确认的三个选择

1. **1A**：M07权威formal主榜所有`ranked_entries`都建事件；`selected_entries`只决定是否有计划。
2. **2A**：入榜日立即建事件，下一开盘出现后追加M08计划决定／计划引用。
3. **3A**：影子期使用调用者注入的稳定非空`author_id`和时间，不建设账号系统；真实权限与UI留给M12。

该批准只覆盖A—E影子实施与本地审核，不包含生产迁移、部署、M10、M11或M12。
