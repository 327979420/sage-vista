# M07｜版本化评分政策与唯一权威排行设计

- 关联需求：`CR-2026-09-01-047`，并接收`CR-2026-09-01-043`的M07历史保护责任
- 状态：`verified`（审核分支影子范围；尚未独立审核、合并、部署或生产启用）
- 基线：`8e18263c8ecaf1f29268378881b1739aeea99701`
- 边界：用户已授权并完成A—E影子实施；本文件不授权部署或生产切换

本地证据：设计`7fa6e59`、实现`8a773e8`、测试`4c1acdb`；完整验收见`docs/M07_ACCEPTANCE_REPORT_ZH.md`。`verified`只表示获批影子范围已实现并通过本地检查，不表示权威排行已经上线。

## 人话版

M03—M06已经把门票、因子、两个模型和行业背景分别装进有编号的盒子。M07只做两件事：拿一张有版本的“评分说明书”计算逐股分项，再用一张有版本的“排序说明书”生成当天唯一复杂多因子主榜。

V1换成V2时，系统新增一套结果，不擦掉V1。历史上的正式榜单永远保留当时版本；把V2拿去重算旧日期只能叫影子比较，不能冒充当时发布的结果。

## 1. 当前链路与需要收口的重复

| 当前入口 | 当前行为 | M07处理 |
| --- | --- | --- |
| `services/scanner/factor_scoring.py::experimental_score()` | 从旧因子状态计算实验分、冗余封顶和不计分原因 | 旧生产兼容保留；新formal评分只由版本化政策驱动 |
| `services/scanner/unified_v2_scan.py::_resonance_summary()` | 重新整理因子并计算颗数、家族、父子和周期奖金 | M07只读M04／M05事实，不重新检测因子 |
| `unified_v2_scan.py::_candidate()` | 同时检查旧门票、计算分数、读取旧市场／行业调整 | 新formal只读M03—M06身份和事实，不复制上游生产逻辑 |
| `unified_v2_scan.py::_rank_day()` | 在同一函数中筛选、排序、截断并生成精选 | 排序、同分键和截断改由唯一`RankingPolicy`表达 |
| `unified_v2_scan.py::_write_report()` | 按日期合并旧网页归档，模型变化时保护部分历史 | 旧JSON保持只读；新快照按内容身份只追加，不以日期覆盖 |

当前问题不是必须立刻改变分数，而是公式、排序、历史保护和网页产物混在旧消费者中。没有独立政策身份，就无法准确回答“这只股票是按V1还是V2得到这个名次”。

## 2. 一句话职责与唯一生产者

> M07只把M03—M06已经验证的客观事实按版本化政策转换为不可变逐股评分，并生成唯一复杂多因子权威排行快照。

推荐中立目录：`services/ranking/`。

- 只有该目录的唯一编排器可以创建formal `score_result_id`和`ranking_snapshot_id`。
- 每日影子与回放影子调用同一纯评分函数和同一纯排序函数。
- 页面、回测、扫描器、个人形态和研究脚本不得复制评分公式或排序键。
- M07不重新创建Gate、TechnicalEvidence、ModelAssessment或ContextSnapshot。

目标链路：

```text
M03 GateEvent 2.x
+ M04 TechnicalEvidence 2.x
+ M05 complex_multifactor ModelAssessment 2.x
+ M06 ContextSnapshot 2.x
+ 版本化ScorePolicy / RankingPolicy
→ services/ranking/唯一生产器
→ ScoreResult 2.x
→ RankingSnapshot 2.x（唯一复杂多因子主榜）
```

## 3. 输入与失败关闭

formal批次必须满足：

1. 所有输入均为已知2.x主版本并使用`path_status=formal`；旧1.x或legacy不能进入formal。
2. 同一证券的Gate、因子、复杂多因子判断和上下文必须绑定相同`instrument_id`、`as_of`、`universe_id`、个股`market_snapshot_id`和M02复权政策。
3. `GateEvent`、完整`TechnicalEvidence`集合、`complex_multifactor`判断和`ContextSnapshot`必须一一可追溯；缺失、重复、跨事件引用或内容指纹不一致时失败关闭。
4. M05的`favorite_pattern`判断不进入复杂多因子主榜评分；它继续独立存在，也不得被自动转成第二张权威榜。
5. formal股票池或任何必要身份缺失时整批失败，禁止自动回退legacy。
6. 只有业务政策明确允许的逐股缺失才能按该政策记录为`unavailable`或排除；不得静默当成零分。

## 4. 版本化评分政策

`ScorePolicy`是集中、不可变的评分说明书，不是散落在消费者中的常量。最小内容包括：

- `score_policy_version`与规范内容指纹；
- 接受的合同主版本、`model_id=complex_multifactor`及适用路径；
- 分项名称、事实来源、方向、权重、阈值、封顶和父子／冗余处理；
- 每个分项的缺失值行为：失败、排除或明确`unavailable`；
- 风险事实怎样单列，是否影响总分；
- M06上下文只保存引用，首个影子政策贡献固定为零且不改变排序；未来改变必须使用新政策并另行批准；
- 总分尺度、舍入规则和规范化顺序；
- 生效范围、批准证据和是否仅为`shadow`。

版本规则：

- 改变分数含义、尺度、资格范围或输入语义：升级主版本。
- 改变权重、阈值、分项、封顶或缺失处理：至少升级次版本。
- 只改不影响规范结果的说明文字：可升级修订版本；内容指纹仍必须更新。
- 任何会改变结果的配置变化都必须生成新政策版本和新`ScoreResult`，禁止覆盖旧结果。
- 未知政策版本、版本与内容指纹不符或未登记配置必须失败关闭。

首个迁移政策只允许复现当前已批准的技术共振分项；不在M07重构中研究新权重。M06上下文贡献固定为零且不参与排序，不能由调用者临时改变。

## 5. ScoreResult 2.x

每个复杂多因子判断在一个明确评分政策下产生一条不可变派生记录。最小字段：

```json
{
  "schema_version": "2.0.0",
  "score_result_id": "score:sha256:...",
  "as_of": "YYYY-MM-DD",
  "path_status": "formal",
  "instrument_id": "instrument:sha256:...",
  "gate_event_id": "gate:sha256:...",
  "technical_evidence_ids": ["evidence:sha256:..."],
  "model_assessment_id": "assessment:sha256:...",
  "context_snapshot_id": "context:sha256:...",
  "score_policy_version": "1.0.0",
  "score_policy_fingerprint": "sha256:...",
  "components": [],
  "total_score": 0,
  "warnings": [],
  "missing_facts": [],
  "score_input_fingerprint": "sha256:...",
  "future_data_used": false
}
```

`components`逐项保存事实引用、政策条目、原始值、变换、贡献、封顶和未计入原因。总分不能代替分项证据。生成时间不进入身份；相同输入和政策必须得到相同身份与内容，相同身份不同内容必须报冲突。

改变评分政策只新增`ScoreResult`。它不能改变GateEvent、TechnicalEvidence、ModelAssessment、ContextSnapshot或旧评分记录。

## 6. RankingPolicy与确定性排序

`RankingPolicy`只负责：

- 哪个`ScoreResult`集合可进入复杂多因子主榜；
- 总分和分项的明确排序方向；
- 完整、版本化的同分键；
- 最终稳定键使用`instrument_id`，不依赖输入顺序、文件顺序或可变化ticker；
- 排除原因与候选截断规则；
- 精选是否为主榜的严格有序子集。

评分政策和排序政策分开版本化。只改同分规则、截断或精选门槛时，不伪装成评分公式变化；仍会生成新的排行快照。

个人形态不消费`RankingPolicy`，不产生`rank`，也不与复杂多因子争夺“权威主榜”。

## 7. RankingSnapshot 2.x与唯一权威语义

每个快照必须绑定：

- `as_of`、formal／legacy路径、`universe_id`和行情身份；
- 完整Gate事件集合及批次审计身份；
- TechnicalEvidence批次、注册表和检测政策版本；
- complex `ModelAssessment`批次、模型版本；
- ContextSnapshot批次、ETF注册表和成分版本；
- `score_policy_version`、`ranking_policy_version`及内容指纹；
- 规范排序后的全部`score_result_id`；
- 代码／运行身份若调用层能提供；缺失时写`unknown`，不得猜测。

快照内部包括：

- `ranked_entries`：逐股名次、总分、分项、完整排序键、理由和警告；
- `excluded_entries`：同批未入榜证券及唯一首要排除原因；
- `selected_entries`：若政策定义精选，则必须是`ranked_entries`的严格有序子集；
- 批次守恒：每个输入复杂多因子判断恰好进入`ranked_entries`或`excluded_entries`一次。

身份规则：

```text
ranking_snapshot_id = hash(
  as_of + path_status + universe/market identities
  + sorted(score_result_ids)
  + score_policy identity + ranking_policy identity
  + authority_scope
)
```

同一完整输入和政策的重复运行是幂等重放，只能得到同一快照。相同身份不同内容是真冲突。输入、政策或证据修订变化必须产生新快照，旧快照不得删除、覆盖或原地修改。

## 8. V1→V2、唯一权威与CR-043历史保护

同一日期可以保存多个策略版本的不可变快照，但权威状态必须唯一：

- 追加式政策生效记录为每个日期／范围明确指定至多一个`authoritative`组合；其他版本只能是`shadow`或`comparison`。
- V2获批后只影响其明确生效日期及以后；历史V1权威快照不重算、不改名、不被V2覆盖。
- 用V2重放V1历史日期时，新快照必须标为`comparison`并引用原V1快照；它不能冒充当时发布结果。
- 同一批输入、同一政策和同一权威范围出现两份不同权威快照时失败关闭。
- 政策生效记录必须带用户批准依据；“最新版本”不是自动权威选择规则。

M07只冻结并产生排行快照。以下CR-043内容继续延后：

- M08：交易计划、入场、止损、持仓和退出；
- M09：一本事件总账、人工追加审核和跨事件查询；
- M10：回测、前向收益、MFE／MAE、Excel和跨版本表现比较；
- M11：从人工案例到独立验证再到新策略版本的升级闸门。

后续模块只能追加引用M07快照，不得反向修改评分或排行历史。

## 9. legacy迁移、影子存储与回退

- 当前`public/unified-v2-rankings.json`、`public/unified-v2-latest.json`和旧评分逻辑保持原样运行。
- 旧JSON只通过一个只读适配入口形成显式legacy视图；缺少Gate／Universe／行情／模型／上下文身份时保留`unknown`和偏差，不补造formal证据。
- M07实施期只在内存、测试临时目录或被忽略的`work/m07-ranking-shadow/`进行内容寻址、只追加写入；同一路径已有不同字节时失败。
- M07完成不创建生产排行文件，不修改工作流、网站或Discord。真实候选目录、Manifest、部署和线上切换仍属于M12。
- 影子结果不一致时停用M07影子入口即可；旧生产排行和历史JSON不受影响。

## 10. 影响与明确不影响

| 模块 | M07设计影响 | 明确不影响 |
| --- | --- | --- |
| M01 | 未来增加评分与排行合同验证 | 不改其他合同 |
| M02 | 只读股票池、行情和复权身份 | 不下载、不写缓存、不倒填历史 |
| M03 | 只读GateEvent／GateScanAudit | 不改门票、长期状态或事件身份 |
| M04 | 只读TechnicalEvidence | 不重算因子、不改注册表 |
| M05 | 只读complex ModelAssessment | 个人形态保持独立，不重算判断 |
| M06 | 只读ContextSnapshot | 不重算ETF状态或成分映射 |
| M07 | 版本化评分、唯一复杂主榜、不可变快照 | 不计算交易或收益 |
| M08 | 无 | 不生成交易计划或trade-ready结论 |
| M09—M11 | 只预留不可变引用 | 不建总账、不评价、不导出Excel、不实施升级闸门 |
| M12／生产 | 无 | 不改工作流、网站、Discord、Manifest或公开JSON |

## 11. 机械验收矩阵

1. 全仓清单证明只有`services/ranking/`创建formal评分和排行身份。
2. formal只接受身份一致的M03—M06已知2.x输入；legacy、未知主版本和自动回退失败。
3. M07不调用Gate、因子检测、模型判断或ETF状态计算函数。
4. 同一输入与政策在不同输入顺序和`PYTHONHASHSEED`下得到相同ScoreResult与RankingSnapshot。
5. 每日影子与回放影子对相同输入调用同一生产器并得到同一身份和内容。
6. V1和V2可同时保存；生成V2前后V1文件字节、身份、名次和分项不变。
7. 同一日期的V2历史重放只能标为`comparison`，不能替代原V1权威快照。
8. 同一权威范围出现两个不同快照失败；幂等重放安全返回原身份。
9. 所有复杂多因子输入逐股守恒到排行或明确排除，重复、遗漏和未知排除原因失败。
10. 每条分项、警告、理由和排除原因都能追溯Gate、TechnicalEvidence、ModelAssessment、ContextSnapshot及政策条目。
11. 缺失事实按政策显式处理，不能静默记零；内容指纹或引用不一致失败。
12. 同分排序使用完整可见排序键，最终稳定键为`instrument_id`；输入或文件顺序不影响名次。
13. 精选若启用，必须是主榜严格有序子集；空精选不能用旧日结果填充。
14. favorite_pattern不进入复杂主榜、不生成竞争rank，也不改变主榜身份。
15. 修改权重、阈值或公式产生新政策和新ScoreResult；修改排序键或截断产生新RankingSnapshot；旧结果均保留。
16. 旧JSON适配前后字节一致，缺失身份不补造，不能进入formal消费者。
17. 输出不得包含TradePlan、交易结果、ForwardOutcome、MFE、MAE、人工审核或Excel结构。
18. 默认每日、夜间、网站、Discord、工作流、公开JSON和当前生产结果零变化。

## 12. 未来实施小包（均预计不超过20分钟）

1. 包A：更新评分／排行规则，冻结政策注册、ScoreResult／RankingSnapshot合同和formal失败关闭。
2. 包B：建立`services/ranking/`纯评分政策注册表、验证器和当前行为等价的影子评分器。
3. 包C：建立唯一确定性排行生产器、逐股守恒和内容寻址只追加影子存储。
4. 包D：建立旧JSON唯一legacy适配器、每日／回放同源影子入口和V1／V2并存反例。
5. 包E：完整本地验收、固定样本逐项对照、独立审核材料和分开提交；不部署、不生产切换。

## 13. 回退

M07只新增影子入口和影子存储。任何合同、分项或排序差异无法解释时，停止影子调用并保留反例；旧`unified_v2_scan.py`、历史排行、公开JSON和生产消费者继续原样运行。不得为了让测试通过而重写旧历史。

## 14. 等待用户确认的选择

1. 已批准：首个formal影子政策只复现当前技术共振分项，不引入新权重；M06上下文单独保存、贡献为零且不改变排序。
2. 推荐：策略V2从获批生效日向前产生新权威快照；重算旧日期只能保存为`comparison`，绝不替换V1。
3. 推荐：M07先实现`work/`内容寻址只追加影子存储；生产永久目录、Manifest和发布切换留给M12，总账引用留给M09。

用户已批准三项推荐选择并授权A—E连续影子实施。该授权不包含合并前跳过独立审核、部署、生产接入、真实历史重算或M08以后模块。
