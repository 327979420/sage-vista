# M11｜策略验证、批准与退休闸门本地验收

状态：`verified`（审核分支）

验收日期：2026-09-06

对应需求：`CR-2026-09-05-051`

## 验收结论

M11 A—D已在获批影子范围完成本地固定合成样本验证。本结论不代表合并`main`、真实策略有效、部署或生产启用。

## 唯一生产层与合同

- 唯一实现位于`services/playbook/`。
- 权威事实为`StrategyProposal 2.0.0`、`StrategyEvidenceAssessment 2.0.0`和`StrategyLifecycleEvent 2.0.0`。
- `StrategyRegistrySnapshot 2.0.0`只是从前三类完整链可再生成的只读视图，不保存第二份最终状态。
- 实现、评估和生命周期记录均使用严格版本、规范化身份、内容指纹和线性只追加修订。

## 机器证据闸门

- Proposal只允许已落盘M09 `hypothesis`或`approved_change`来源；`observation`不得直接晋级。
- Assessment只从真实落盘的M09和M10影子存储重新读取并验证权威证据；未落盘对象、裸ID和仅格式合法的SHA不足够。
- 必须有completed ExperimentRun、完整结果集、formal无bias路径、数据／股票池／复权政策、候选／基线版本、全部预登记分区及至少一个独立`validation`或真实`forward`案例。
- 必需证据不足为`evidence_incomplete`；标准失败为`not_validated`，已验证后被新失败证据推翻则为`invalidated`。没有全局收益阈值。
- CGEM、MRNA、BTDR、DLTR、ADBE、BABA、TTD和AEVA在固定样本中不得改标为新独立验证。

## 四轴和生命周期

- 机器证据、用户决定、main实现和生产状态四轴独立。
- 用户可在尚未`validated`时批准候选实现，但不改写机器证据，也不能成为`active`。
- `implemented_in_main`必须具有精确代码提交、规则版本和测试证明，仍不等于生产。
- `active`还必须由M12提供Manifest、部署和线上验证证明；M11本轮未创建任何真实M12证明。
- 退休只追加并保留原active历史；已退休版本不得原地复活。V1与V2永久并存。

## 测试证据

- M11专项：31项通过。
- M09—M11联合定向：228项运行，218项通过、10项跳过。
- M01—M11扩大定向：394项运行，384项通过、10项跳过。
- 完整Python：761项运行，751项通过、10项跳过。
- `PYTHONHASHSEED=0／1／42／12345`：每轮31项通过。
- 治理合同：19项通过。
- 前端：11项通过；lint、TypeScript和生产构建通过。
- Python编译、文档链接和`git diff --check`通过。

## 范围确认

- 本轮没有读取行情、访问EODHD、运行真实实验／回测，也没有计算新指标。
- 没有改写M03—M10事实、规则、代码或生产配置。
- 没有修改网站、Discord、工作流、公开JSON或生产入口。
- M12、M13、VectorBT和看板均未开始。
- CR-043继续为`captured`。
