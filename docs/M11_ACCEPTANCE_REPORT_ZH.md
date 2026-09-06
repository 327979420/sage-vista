# M11｜策略验证、批准与退休闸门本地验收

状态：`verified`（仅本地合成验收；等待全新独立审核，审核分支）

验收日期：2026-09-06

对应需求：`CR-2026-09-05-051`

## 2026-09-06 criterion身份自证修复

- 审核基线：`751cc3ebfe4cf5ba3342c503baaac648047d1e72`。基线实测：固定合成baseline criterion分别使用`forward_outcome_id`和`forward_content_fingerprint`，expected填实际结果ID／指纹，经合成可信预登记后均为`validated`，`write_proposal`和`write_assessment`均接受。
- 修复只在`services/playbook/contracts.py`的预登记合同入口集中增加四种结果合同的业务字段、数值类型及封闭状态枚举允许表；未修改消费者。规则11升级`1.2.1`，schema和来源版本不变，不重写历史。
- 两个反例覆盖构造器、直接合同验证、评估、公共Proposal写入，以及模拟旧漏洞写入的canonical Proposal被重新读取时的公共Assessment写入；均应在criterion验证处拒绝。
- 合法状态、指标eq/gte/lte和计数可评估并落盘；错误类型、等价身份／指纹字段、自由文本与嵌套路径拒绝。零匹配仍unavailable，多匹配失败关闭，旧2.0／2.1只读边界由既有专项回归覆盖。
- 本轮验证：M11专项60项通过；完整Python运行790项，780通过、10跳过；PYTHONHASHSEED=0／1／42／12345每轮60项通过；前端11项、lint、TypeScript、生产构建、Python编译、变更文档链接与`git diff --check`通过。机器状态重新生成内容与CURRENT_STATUS完全一致。以下历史测试数字属于先前收口，并非本次独立审核结论。
- 提交证据：本节与修复代码同属独立提交`fix: restrict M11 criteria to typed business fields`（父提交751cc3e）；最终完整SHA由交付消息及Git记录提供。审核分支`m11/strategy-promotion-gate-5859d12`。
- 仅本地合成样本；没有审核bot数据、合并、部署、真实策略晋级或生产启用。完成后留在审核分支，交全新独立审核。

## 先前验收结论

M11 A—D已在获批影子范围完成本地固定合成样本验证。本结论不代表合并`main`、真实策略有效、部署或生产启用。

## 唯一生产层与合同

- 唯一实现位于`services/playbook/`。
- 当前formal写入使用`StrategyProposal 2.2.0`、`StrategyEvidenceAssessment 2.2.0`和`StrategyLifecycleEvent 2.2.0`；旧`2.0.0／2.1.0`只读，不能进入新的formal评估或存储。
- `StrategyRegistrySnapshot 2.2.0`只是从前三类完整链可再生成的只读视图，不保存第二份最终状态；旧`2.0.0／2.1.0`同样只读。
- 实现、评估和生命周期记录均使用严格版本、规范化身份、内容指纹和线性只追加修订。

## 机器证据闸门

- Proposal只允许已落盘M09 `hypothesis`或`approved_change`来源；`observation`不得直接晋级。2.2还必须绑定可信预登记记录，证明完整提议、证据范围和全部criterion早于每个相关M10 pending运行冻结。
- Assessment只从真实落盘的M09和M10影子存储重新读取并验证权威证据；未落盘对象、裸ID和仅格式合法的SHA不足够。
- 必须有completed ExperimentRun、完整结果集、formal无bias路径、数据／股票池／复权政策、候选／基线版本、全部预登记分区及至少一个独立`validation`或真实`forward`案例。
- 必需证据不足为`evidence_incomplete`；标准失败为`not_validated`，已验证后被新失败证据推翻则为`invalidated`。没有全局收益阈值。
- `case_label`和ticker只作显示；是否已见及validation／forward资格只由M09稳定事件身份和可信案例登记决定。换成已知ticker文字不会把未见案例变成已见，改成“UNSEEN”也不能隐藏真实已见案例。

## 独立审核修复

- 四项权威性修复及回归测试代码提交为`e63412817f1ee9dc36a2aa10cedf807fd71d2600`。
- 预登记现在冻结预期运行、必需分区／结果族／窗口、候选与基线版本、数据、股票池、政策及时间范围。Assessment从M10冻结库存确定性重推完整全集，再与声明逐项比较；遗漏不利运行、窗口或分区，增加／替换／重复运行，跨政策或跨结果族均失败关闭。
- Proposal案例角色绑定已落盘M09事件的`event_id`、稳定`instrument_id`、`signal_date`和内容指纹；`seen_before`由显式可信案例登记解析，显示标签、ticker别名和调用方声明不能改变案例身份或已见状态。
- 用户批准、main实现和M12激活事件必须经显式可信解析器重新验证。默认formal路径没有解析器即失败关闭；固定合成测试只能使用标记为`test`的解析器。M12尚未实施，因此真实formal `active`不可达。
- RegistrySnapshot在同一库存锁内从完整Proposal、Assessment和Lifecycle库存重建，并与待写入快照作规范字节比较；公共存储不能接受删项、增项、替换、重复或重签后的不完整快照。

## 最终两项收口修复

- 代码提交`ffda522`将current formal合同升级为严格`2.2.0`，来源版本升级为`m11-shadow-1.2.0`；`2.0.0／2.1.0`继续按原字段只读。
- `PreregistrationAuthorityResolver`必须返回完整、内容寻址的冻结记录，绑定完整Proposal业务语义、登记时间、登记提交及覆盖的M10运行代码提交。评估同时验证登记时间早于每个pending根`started_at`，并要求可信解析器确认登记提交先于对应运行提交；默认无解析器失败关闭。
- 2.2 criterion只允许以结果合同、candidate／baseline角色、分区、Forward窗口、字段、操作符和阈值作运行前语义选择；不得保存运行后才出现的Outcome ID或内容指纹。评估从M10完整库存匹配唯一结果，零匹配为证据不足，多匹配失败关闭，不重算收益或指标。
- `case_label`硬编码名单已退出合同判断；标签仍进入Proposal内容指纹，但不改变稳定案例身份、`seen_before`或案例资格。

## 四轴和生命周期

- 机器证据、用户决定、main实现和生产状态四轴独立。
- 用户可在尚未`validated`时批准候选实现，但不改写机器证据，也不能成为`active`。
- `implemented_in_main`必须具有精确代码提交、规则版本和测试证明，仍不等于生产。
- `active`还必须由M12提供Manifest、部署和线上验证证明；M11本轮未创建任何真实M12证明。
- 退休只追加并保留原active历史；已退休版本不得原地复活。V1与V2永久并存。

## 测试证据

- M11专项：54项通过。
- M09—M11联合定向：251项运行，241项通过、10项跳过。
- M01—M11扩大定向：417项运行，407项通过、10项跳过。
- 完整Python：784项运行，774项通过、10项跳过。
- `PYTHONHASHSEED=0／1／42／12345`：每轮54项通过。
- 治理合同：19项通过。
- 前端：11项通过；lint、TypeScript和生产构建通过。
- Python编译、文档链接和`git diff --check`通过。

## 范围确认

- 本轮没有读取行情、访问EODHD、运行真实实验／回测，也没有计算新指标。
- 没有改写M03—M10事实、规则、代码或生产配置。
- 没有修改网站、Discord、工作流、公开JSON或生产入口。
- M12、M13、VectorBT和看板均未开始。
- CR-043继续为`captured`。
- 当前真实formal validated、active和新增alpha hard rule数量均为0。
