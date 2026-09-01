# M05｜两个选股器与统一模型判断设计

状态：`implementing`（三项推荐选择已批准；A—E连续影子实施）  
CR：`CR-2026-09-01-045`  
基线：`dbb867202b5f0380c58d32190c9b68ff944233f2`  
设计分支：`m05/selectors-dbb8672`

> 用户已批准本设计的三项选择并授权A—E连续影子实施。实施完成仍不等于部署或生产启用。

## 人话版

M03已经发出同一张“候选票”，M04已经准备好同一盒“因子证据”。M05只让两位选股师傅阅读这张票和这盒证据：

- 复杂多因子师傅整理“看到了哪些客观技术事实”；
- 个人形态师傅整理“这四步形态走到哪里、缺什么、被什么风险挡住”。

两位师傅可以得出不同判断，但不能重新算MACD、长期资格或共享因子。M05不负责给分、不排榜、不写交易计划。

## 1. 当前重复与真实入口

### 复杂多因子

- `services/scanner/unified_v2_scan.py::_candidate()`从旧`daily-factor-snapshot.json`再次判断MACD与长期资格，并重组因子命中。
- `_resonance_summary()`、`_timeframe_profile()`和`_factor_ledger()`把事实整理、颗数、奖励、评分和排行混在同一旧入口。
- `_rank_day()`还读取市场、行业并排序；这些分别属于M06和M07，不属于M05。

### 我最喜欢形态

- `services/scanner/resonance_tracker.py::run()`直接准备行情并调用`favorite_pattern_tracker.evaluate()`。
- `services/scanner/favorite_pattern_tracker.py`同时保存V1、V2、V3检测、风险、图表、序列化与展示筛选；它直接从OHLCV计算双底、三推、EMA和回撤。
- 其中一部分概念与M04因子同名但定义并不完全相同。例如V3宽口径双底不能冒充注册表中的窄口径双底。

### 要解决的问题

当前两个入口可以各自重新判断门票和技术事实，容易让每日与回放、复杂多因子与个人形态得到两套解释。M05应建立一个模型判断出口，同时保留定义差异，不能为了“统一”把不同事实假装成同一个事实。

## 2. 一句话职责与唯一负责人

M05只负责：**把同一GateEvent和同一批TechnicalEvidence解释为两个独立、不可变、无评分的ModelAssessment。**

未来中立目录为`services/selectors/`：

- 一个编排器负责验证输入、调用两个分析器、生成唯一`assessment_id`；
- `complex_multifactor`分析器只整理共享技术证据；
- `favorite_pattern`分析器只整理V3四步组合、缺项和风险；
- 只有编排器可以创建新的formal `ModelAssessment 2.x`身份。

## 3. 输入

formal输入必须同时满足：

1. 一个已验证的`GateEvent 2.x`；
2. 该事件对应的完整`TechnicalEvidence 2.x`集合；
3. 相同的`instrument_id`、`as_of`、`path_status=formal`、`universe_id`、`market_snapshot_id`和M02复权政策；
4. 当个人形态确需计算“定义不同的专属组合事实”时，只能读取GateEvent已经绑定的M02不可变点时行情，不得另取缓存、今天名单或网络行情。

任何身份不一致、证据缺项、未知合同主版本或未来数据必须失败关闭。formal缺失时不能自动改走legacy。

## 4. 输出：ModelAssessment 2.x

每个GateEvent可以产生两条互不覆盖的判断：

- `model_id=complex_multifactor`
- `model_id=favorite_pattern`

建议必填字段：

```json
{
  "schema_version": "2.0.0",
  "assessment_id": "assessment:sha256:...",
  "as_of": "2026-08-28",
  "generated_at": "2026-09-01T00:00:00Z",
  "source_version": "m05-shadow-1.0.0",
  "future_data_used": false,
  "gate_event_id": "gate:sha256:...",
  "instrument_id": "instrument:sha256:...",
  "model_id": "complex_multifactor",
  "model_version": "1.0.0",
  "path_status": "formal",
  "eligible": true,
  "status": "assessed",
  "technical_evidence_ids": ["evidence:sha256:..."],
  "matched_facts": [],
  "missing_facts": [],
  "risk_facts": [],
  "warnings": [],
  "model_specific_facts": {},
  "production_effect": false
}
```

`assessment_id`规范绑定：GateEvent、模型ID、模型版本、formal／legacy路径、规范排序后的证据ID及模型专属事实指纹。相同输入重复运行身份与内容必须相同；同一身份下内容不同必须报冲突。

明确禁止输出：

- 综合分、权重、奖励或收益概率；
- rank、榜单截断或精选结果；
- 大盘、行业或热度调整；
- 入场、止损、目标、持仓或退出；
- 机会总账、前向结果或Excel评价。

## 5. 两个分析器各自负责什么

### 5.1 复杂多因子

只整理M04已经生产的客观事实：

- 命中／未命中／不可用；
- 因子家族覆盖；
- 父子依赖是否满足；
- 日、周、月证据及首次确认日；
- 正向事实与风险事实分栏；
- 缺失或阻断原因。

它不再计算技术分、周期奖金、共振加分或排名。旧`unified_v2_scan.py`中的分数与排序保持原生产行为，留给M07迁移，不在M05复制。

### 5.2 我最喜欢形态

formal影子判断只表达V3四项进度：

1. 客观回调；
2. 宽口径双底；
3. 三推下降趋势线完整收盘突破；
4. Golden Pocket或EMA20／50／200承接；
5. 另列风险阻断。

处理规则：

- 与M04机器定义完全相同的事实直接引用对应`evidence_id`，禁止重算；
- 名称相近但定义不同的V3事实必须放入`model_specific_facts`，带定义版本、点时证据和输入指纹，禁止冒充M04因子；
- 四项完成数只表示形态进度，不是分数或收益概率；
- V1静态七项和V2两段七阶段只通过一个只读legacy适配器保留，不进入formal 2.x；
- 当前个人形态生产页在M05影子期完全不变。

## 6. GateEvent共同入口与兼容边界

- 两个formal分析器只能从同一GateEvent开始；个人形态不得另建候选事件。
- 同一股票同一天仍只有一个GateEvent；两条ModelAssessment只是对同一事件的不同只读解释。
- 当前V3生产页“不要求当天MACD刚金叉”的广口径观察继续作为legacy现状保留，不冒充formal M05结果。
- GateEvent 1.x、TechnicalEvidence 1.x、旧Unified V2和旧个人形态产物只能经各自唯一只读适配器进入legacy研究；不得补造缺失身份升级为formal。
- M05只做影子产物；真实生产切换属于M12。

## 7. 每日与回放同源

目标调用链：

```text
M02不可变点时输入
→ M03 GateEvent 2.x
→ M04 TechnicalEvidence 2.x
→ services/selectors/唯一编排器
   ├─ complex_multifactor ModelAssessment
   └─ favorite_pattern ModelAssessment
```

每日影子入口与回放影子入口只传入不同批次身份，必须调用同一编排器和相同分析器。任何消费者不得自行重算门票、共享因子或assessment身份。

## 8. 影响与明确不影响

| 模块 | 本次设计影响 | 明确不影响 |
| --- | --- | --- |
| M01合同 | 未来严格验证ModelAssessment 2.x | 不改其他合同 |
| M02行情／股票池 | 仅只读已冻结点时身份与必要不可变行 | 不下载、不写缓存、不改股票池 |
| M03门卫 | 只读GateEvent | 不改MACD、长期资格或Gate身份 |
| M04因子事实 | 只读TechnicalEvidence | 不新增、重算或改定义 |
| M05两个选股器 | 新建唯一无评分判断层 | 不产生第二张Gate票 |
| M06 | 无 | 不读大盘、行业或热度 |
| M07 | 无 | 不评分、不排名、不截断 |
| M08 | 无 | 不生成交易计划 |
| M09—M10 | 无 | 不写总账、不做评价或Excel |
| M12／生产 | 无 | 不改工作流、网站、Discord、公开JSON |

## 9. 机械验收

1. 同一GateEvent与同一TechnicalEvidence重复运行得到相同两条assessment身份和内容。
2. complex与favorite可对同一GateEvent给出不同状态，但不得创建新GateEvent。
3. formal只接受GateEvent 2.x与TechnicalEvidence 2.x，身份不一致失败。
4. formal缺失时不自动回退legacy。
5. 两个分析器不得调用M03门卫或M04共享因子检测器。
6. M03已有事实和M04共享事实只能以ID引用一次。
7. 个人形态定义不同的专属事实必须显式标记，不得冒充注册因子。
8. V1／V2旧个人形态只读适配前后字节不变。
9. 固定小样本上，旧复杂多因子客观命中清单与新assessment一致；分数和排名不属于对照对象。
10. 固定小样本上，V3四项、缺项、风险和阶段与旧检测行为一致；若不一致立即停止。
11. 缺失必需证据返回`unavailable`或失败，不猜测为false或零。
12. `production_effect`固定为false，输出中不得出现score、rank、TradePlan或ContextSnapshot。
13. 每日与回放对相同输入得到相同assessment身份。
14. 不同`PYTHONHASHSEED`和输入顺序不改变身份。
15. 默认每日、夜间、网站、Discord、工作流和公开JSON逐字节不变。

## 10. 迁移与回退

- M05只新增影子入口，不替换现有`unified_v2_scan.py`或`favorite_pattern_tracker.py`生产调用。
- 旧文件继续只读；不重写历史事件、排名或个人形态记录。
- 影子验证失败时删除或停用新入口即可，旧生产路径不受影响。
- 只有M12另行批准后，生产消费者才可能切换；M05完成不代表上线。

## 11. 未来实施小包（均预计不超过20分钟）

1. 包A：冻结M05规则、`ModelAssessment 2.x`合同、身份与失败关闭测试。
2. 包B：建立`services/selectors/`唯一编排器和复杂多因子无评分分析器。
3. 包C：建立V3个人形态兼容分析器及V1／V2唯一legacy只读适配器。
4. 包D：给每日与回放增加未接默认流程的同源影子入口，并完成重复生产者清单测试。
5. 包E：完整本地验收、固定案例、确定性检查和治理证据；分开提交供独立审核。

## 12. 已批准选择

用户已于2026-09-01确认以下三项：

1. formal个人形态只处理同一GateEvent；当前更宽的“无需当天MACD”观察继续明确保留为legacy，不进入formal。
2. 共享定义只引用TechnicalEvidence；个人形态定义确有差异时允许保存为带版本的`model_specific_facts`，不能假装成同一因子。
3. `ModelAssessment 2.x`只保存客观判断、缺项、风险和解释；所有分数、排名、上下文和交易计划分别留给M07、M06和M08。

状态：已批准实施A—E；M06、M07、M08、M09、M10和M12仍未授权。
