# M08｜统一模拟交易计划与退出状态设计

- 关联需求：`CR-2026-09-01-048`
- 状态：`implemented`（获批影子范围已完成实现、测试、独立审核并进入`main`；尚未部署或生产启用）
- 基线：`6e63634be6650f94a80d1f11935ed437c2f00abe`
- 边界：用户已批准A—E连续影子实施；不授权部署或生产接入

## 人话版

M07已经给出一张有版本、不会覆盖旧结果的排行榜。M08像一位只按说明书办事的模拟交易员：对获准建立计划的排行条目，等到下一交易日真实开盘价出现后，冻结入场、止损、2R目标和40日上限；以后每天只按同一套退出规则更新状态。

证据不齐就写`unavailable`，不会猜价格或硬凑计划。30→60→126日延长、2R卖90%留10%和8%追踪仍只是未来实验，首版全部关闭。

## 1. 当前事实与重复位置

| 当前入口 | 已有行为 | M08处理 |
| --- | --- | --- |
| `services/scanner/support_risk.py::signal_support_plan()` | 在信号日只用当时数据冻结最高已确认支撑 | 保持算法等价，收敛到唯一计划生产层 |
| `support_risk.py::executable_stop()` | 下一调整后开盘入场；止损取支撑下5%与入场下10%中较高者；目标2R | 形成版本化`TradePlan 2.x`，不改数值口径 |
| `support_risk.py::simulate_execution()` | 最多40日；跳空按开盘；同日止损和目标均触及时止损优先 | 形成独立退出状态机，不再与收益统计混在一个函数 |
| `services/scanner/factor_snapshot.py` | 把`support_plan`和执行政策写进旧候选 | 旧生产保持；未来影子入口只读统一M08结果 |
| `services/scanner/opportunity_ledger.py` | 同时计算入场、收益、MFE／MAE和策略退出 | M08只负责计划与状态；永久结果和收益留给M09／M10 |
| `research/backtest/annual_factor_summary_v1.py`及其他研究脚本 | 分别调用执行函数或保留自己的退出挑战者 | 旧研究兼容保留；新formal每日与回放只调用一个M08生产器 |

问题不是当前规则一定错误，而是支撑、计划、退出和收益散在扫描、总账及研究脚本中，无法稳定回答“这份计划用了哪版规则”。

## 2. 一句话职责与唯一生产者

> M08只把M07获准建立计划的排行条目和M02点时行情，按现行执行政策生成唯一不可变模拟`TradePlan`，再用同一纯状态机推进退出状态；不计算评分、排名或表现评价。

推荐中立目录：`services/execution/`。

```text
M07 RankingSnapshot 2.x / ScoreResult 2.x
+ M03 GateEvent 2.x引用
+ M02不可变调整后OHLCV与ADJUSTMENT_POLICY
+ 版本化PlanPolicy / ExitPolicy
→ services/execution/唯一生产器
→ TradePlan 2.x
→ ExitState 2.x
```

- 只有该目录可以创建formal `plan_id`和`exit_state_id`。
- 每日影子与回放影子必须调用同一计划函数和同一状态迁移函数。
- M08只引用上游身份，不重新计算Gate、因子、模型、上下文、分数或名次。

## 3. 创建边界与输入

首版只处理`RankingSnapshot.selected_entries`，因为当前治理要求“只有达到交易标准者建立完整计划”；`ranked_entries`中未进入精选前缀者不伪造计划，只在批次审计中记录`not_selected_for_plan`。用户已批准该边界。

formal输入必须同时满足：

1. `RankingSnapshot 2.x`、其内嵌`ScoreResult 2.x`和被引用的`GateEvent 2.x`均为formal、内容指纹有效且身份一致。
2. 排行日期等于信号日；`instrument_id`、`gate_event_id`、`score_result_id`和`ranking_snapshot_id`完整可追溯。
3. M02行情使用完整`ADJUSTMENT_POLICY`，信号日及下一可交易日均不得使用未来修订或未完成日K。
4. 信号日支撑只能由截至信号日的行情冻结；下一日及之后的价格不得回写支撑。
5. 下一可交易日的调整后开盘价、支撑证据和政策内容齐全后才创建完整计划。缺任一项返回计划决定`unavailable`，不创建假的`TradePlan`。
6. formal缺失不能自动回退legacy。旧`support_plan`只能经唯一只读适配器形成显式legacy视图，不能补齐证据进入2.x formal。

支撑接口补充：M04提供只读`SupportEvidenceBatch`，把现有唯一`signal_support_plan()`结果绑定`gate_event_id`、M02行情／股票池身份、M04批次和稳定技术证据ID。M08必须直接读取该证据内容和ID；不得从M07分数、排序理由或文字反推支撑，也不得导入EMA、Fibonacci、pivot、Gate或因子检测函数。若上游缺少必要事实，计划为`unavailable`，不能在M08复制计算。

## 4. 版本化政策

政策集中保存，不允许调用者临时改数字：

- `plan_policy_version`：入场规则、支撑冻结、5%缓冲、10%最大计划损失、2R目标和40日上限；
- `exit_policy_version`：跳空成交、日K触发顺序、同日止损优先和到期收盘退出；
- 两份政策都保存规范内容指纹；任何影响结果的变化必须产生新版本和新身份；
- 首版只复现`support-5pct-cap-10pct-2r-v1`，不创造新阈值或权重；
- 30→60→126日、2R卖90%留10%、8%追踪、双日线／高周期退出及20日挑战者全部列入`disabled_experiments`，固定`production_effect=false`，不得进入首版状态迁移。

## 5. TradePlan 2.x

只有证据完整且风险可执行时才产生完整计划。最小字段：

```json
{
  "schema_version": "2.0.0",
  "plan_id": "plan:sha256:...",
  "as_of": "YYYY-MM-DD",
  "signal_date": "YYYY-MM-DD",
  "entry_date": "YYYY-MM-DD",
  "path_status": "formal",
  "plan_role": "shadow",
  "instrument_id": "instrument:sha256:...",
  "ranking_snapshot_id": "ranking:sha256:...",
  "score_result_id": "score:sha256:...",
  "gate_event_id": "gate:sha256:...",
  "market_snapshot_id": "market:sha256:...",
  "adjustment_policy": {"version": "...", "formula": "..."},
  "entry": {"rule": "next_adjusted_open", "price": 100.0},
  "support": {"frozen_as_of": "YYYY-MM-DD", "level": 95.0, "source": "..."},
  "stop": {"price": 90.25, "rule": "max(support*0.95, entry*0.90)"},
  "target": {"price": 119.5, "r_multiple": 2.0},
  "max_hold_sessions": 40,
  "invalidation_conditions": [],
  "plan_policy_version": "1.0.0",
  "exit_policy_version": "1.0.0",
  "status": "active",
  "future_data_used": false
}
```

身份绑定排行条目、完整上游身份、实际入场证据、冻结支撑、M02复权政策以及计划／退出政策。相同输入和政策必须得到同一`plan_id`；相同身份不同内容失败。每个`ranking_snapshot_id + score_result_id + plan_policy_version + plan_role`最多一份计划，新政策只能新增比较计划，不覆盖旧计划。

计划不保存收益、MFE、MAE、人工意见或Excel字段。缺少关键证据时只返回带规范原因的决定结果，不创建全是`null`的完整计划。

## 6. ExitState 2.x

退出状态与入场评分分开。首版状态机仅有：

```text
active
→ closed_stop_gap | closed_stop | closed_target | closed_time_40d
```

每次推进都只读取计划、上一状态和截至当日已完成的调整后日K，输出不可变新状态；不回写旧状态。状态至少绑定`plan_id`、`previous_exit_state_id`、行情快照、`as_of`、已持有交易日数、当前状态、触发原因和执行价格。

冻结顺序：

1. 当日开盘低于或等于止损：按开盘记录`closed_stop_gap`；
2. 当日最低触及止损：按止损记录`closed_stop`；
3. 当日开盘或最高触及目标：按目标记录`closed_target`；
4. 前39日未退出，第40日按完整收盘记录`closed_time_40d`；
5. 数据不足则保持`active`或返回`unavailable`，不得猜成交。

同日同时触及止损和目标仍先算止损。M08只给出模拟执行状态和价格事实，不计算收益率、R收益、MFE、MAE或绩效汇总；这些由M09／M10只读引用后另行保存和评价。

## 7. 不可变、版本与历史保护

- 计划和状态均内容寻址、只追加；旧政策结果永久保留。
- 新政策重算旧日期只能标为`comparison`，不得冒充当时计划或覆盖旧状态。
- 一个权威排行条目在同一获批计划政策下只能有一份权威计划；两个不同内容争用同一身份时失败关闭。
- 计划政策改变不修改M07排行；退出政策改变不修改计划以外的上游事实。
- 状态链出现分叉、断链、循环、重复身份不同内容或跨计划引用时失败。
- M08影子阶段只在内存、系统临时目录或受保护`work/m08-execution-shadow/`验证；生产永久总账属于M09，生产发布属于M12。

## 8. 影响与明确不影响

| 模块 | M08影响 | 明确不影响 |
| --- | --- | --- |
| M01／M02 | 复用合同验证、日期、指纹、原子写入和调整后行情 | 不下载、不改缓存、不倒填历史 |
| M03—M06 | 只读身份和既有客观事实 | 不重算门卫、因子、模型或上下文 |
| M07 | 只读唯一复杂主榜及政策身份 | 不改评分、名次、精选门槛；个人形态不进入主榜计划流 |
| M08 | 唯一计划生产器、现行退出状态机、影子入口 | 不启用任何延后实验 |
| M09／M10 | 只预留不可变引用 | 不建总账，不算收益／MFE／MAE，不导出Excel |
| M12／生产 | 无 | 不改每日、夜间、网站、Discord、工作流、Manifest或公开JSON |

## 9. 机械验收矩阵

1. 全仓清单证明只有`services/execution/`创建formal计划与退出状态身份。
2. formal只接受身份一致的M02／M03／M07已知2.x输入；legacy和自动回退失败。
3. 只有获准计划的排行条目形成计划；其他条目和缺证据条目不得伪造完整计划。
4. 下一调整后开盘、信号日冻结支撑、5%缓冲、10%风险上限、2R目标和40日上限逐项与旧固定样本一致。
5. 未来价格或行情修订不能反向改变原信号日支撑；证据修订产生新身份而不覆盖旧计划。
6. 缺少开盘价、支撑、行情身份或风险无效时明确`unavailable`。
7. 同日止损与目标同时触发时止损优先；止损跳空、目标和第40日退出与现行行为一致。
8. 相同输入、不同输入顺序和四种`PYTHONHASHSEED`得到相同计划及状态身份。
9. 每日影子和回放影子调用同一生产器，对相同输入得到相同计划与状态。
10. 同一排行条目、政策和角色出现不同计划失败；幂等重放安全；旧版本字节不变。
11. 状态链分叉、断链、循环、跨计划引用和相同身份不同内容失败关闭。
12. formal缺失不回退legacy；旧`support_plan`只读适配前后字节不变且不能进入formal。
13. 所有延后实验固定关闭，不改变止损、目标、仓位或持仓上限。
14. 输出不含评分、排名计算、交易收益、MFE、MAE、人工审核、总账或Excel结构。
15. 默认每日／夜间入口、旧研究结果、工作流、网站、Discord和公开JSON零变化。

## 10. 未来实施包（每包约20分钟）

1. 包A：更新风险执行规则，冻结政策、`TradePlan 2.x`、`ExitState 2.x`和失败关闭语义。
2. 包B：建立`services/execution/`唯一纯计划生产器、验证器及当前行为等价测试。
3. 包C：建立唯一退出状态机、不可变状态链及同日触发／40日反例。
4. 包D：建立旧`support_plan`唯一legacy适配器、每日／回放同源影子入口和只追加影子存储。
5. 包E：完整本地验收、固定样本对照、独立审核材料和分开提交；不部署、不接生产。

## 11. 回退

M08只新增未接默认流程的影子入口。任何固定样本在入场、止损、目标、持仓日或退出顺序上与现行行为不一致，立即停用影子调用并保留反例；旧`support_risk.py`、每日／夜间流程、研究产物和公开JSON继续原样运行。不得为了通过测试而改旧历史。

## 12. 已批准选择

1. 首版只为`selected_entries`建立完整计划；其余已排名条目只记录`not_selected_for_plan`，不生成计划。
2. 完整`TradePlan`等下一调整后开盘价出现后才创建；信号收盘时只保存计划决定和冻结支撑，不提前猜入场、止损或目标。
3. M08可以计算并返回退出状态与模拟执行价，但不计算收益、R收益、MFE或MAE；永久留档和表现评价留给M09／M10。

用户已批准三项选择及A—E影子实施。该授权不包含部署、生产切换、M09／M10／M12实施或任何延后实验。

验收证据：设计`c00e4e8`、实现`cc42569`、测试`75a4d3c`、验收记录`43ccc22`；独立审核通过后已纯fast-forward进入`main`，完整结果见`docs/M08_ACCEPTANCE_REPORT_ZH.md`。`implemented`不表示已经部署或生产启用。
