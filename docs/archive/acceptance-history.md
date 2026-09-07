# M03—M11 历史验收记录

本文件合并保存旧记录，按需追溯，不是当前执行流程或当前生产状态。正文中的“当前”“权威”“已批准”等表述属于原记录时点；现行业务查 [模块规则](../rules/README.md)，实际状态查 [机器来源](../CURRENT_STATUS_ZH.md)。旧文件原件及原行号可从清理前 Git 提交 `875c1d2` 恢复。

## 目录
- [M03_ACCEPTANCE_REPORT_ZH.md](#m03-acceptance-report-zh)
- [M04_ACCEPTANCE_REPORT_ZH.md](#m04-acceptance-report-zh)
- [M05_ACCEPTANCE_REPORT_ZH.md](#m05-acceptance-report-zh)
- [M06_ACCEPTANCE_REPORT_ZH.md](#m06-acceptance-report-zh)
- [M07_ACCEPTANCE_REPORT_ZH.md](#m07-acceptance-report-zh)
- [M08_ACCEPTANCE_REPORT_ZH.md](#m08-acceptance-report-zh)
- [M09_ACCEPTANCE_REPORT_ZH.md](#m09-acceptance-report-zh)
- [M10_ACCEPTANCE_REPORT_ZH.md](#m10-acceptance-report-zh)
- [M11_ACCEPTANCE_REPORT_ZH.md](#m11-acceptance-report-zh)

---

<a id="m03-acceptance-report-zh"></a>

## 原文件：M03_ACCEPTANCE_REPORT_ZH.md

<a id="m03-acceptance-report-zh-m03唯一门卫与长期状态验收及main收口报告"></a>
# M03｜唯一门卫与长期状态验收及main收口报告

日期：2026-09-01
状态：`implemented`（M03获批影子范围；已进入main，未部署、未生产启用）
对应需求：`CR-2026-09-01-042`

<a id="m03-acceptance-report-zh-结论"></a>
## 结论

M03已在批准边界内完成A— I：建立唯一GateEvent生产者、批次级GateScanAudit、行为等价基线门票、0.618／70%局部结构事实、多年回撤、完整周期长期事实、不可变修订链，以及每日和回放的同源影子入口。它没有替换任何生产默认入口。

M03审核成果已经通过纯fast-forward进入`main`，最终main提交为`d02b03295a5e37cebeb788bc780fbede67e574a0`。这里的`implemented`只表示获批影子合同和基础设施已进入主线，不表示部署或生产启用；正式每日扫描、夜间回测、网站、Discord、工作流和公开JSON均未采用M03。

<a id="m03-acceptance-report-zh-提交证据"></a>
## 提交证据

| 提交 | 内容 |
|---|---|
| `74901ac` | 批准M03快速影子实施的治理边界 |
| `10bde71` | GateEvent 2.x、GateScanAudit、基线及影子长期事实、唯一生产器 |
| `f6458b0` | 每日与历史回放同源影子入口 |
| `f722bf5` | 合同反例、修订链、不可变存储、消费者机械清单及回归测试 |
| `140aa18` | GateScanAudit只追加影子存储和同身份冲突保护 |
| `2150b39` | 批次审计幂等、冲突及旧字节不变反例 |
| `170b0a5` | M02完整资格摘要进入M03审计，完整Universe成员总数守恒 |
| `9ccc075` | 多代GateEvent修订链按唯一current解析，不依赖输入顺序 |
| `d02b032` | 最终验收证据；M03通过纯fast-forward进入main的HEAD |
| `ae936c7` | 集成冒烟修复：全局拒绝隐藏循环及其全部输入排列 |
| `88ae7da` | 集成冒烟修复：零eligible formal Universe生成零事件守恒审计 |

<a id="m03-acceptance-report-zh-机械验收结果"></a>
## 机械验收结果

- M01／M02／M03定向：72项通过；
- 完整Python：456项通过；
- Python编译：通过；
- 前端：lint、TypeScript检查、生产构建通过，11项测试通过；
- 确定性：`PYTHONHASHSEED=0/1/42/12345`下，M03定向23项每轮全部通过；
- 补丁格式：`git diff --check`通过；
- Git收口：本地`main`、`origin/main`及本地／远端M03分支均为`d02b03295a5e37cebeb788bc780fbede67e574a0`，合并方式为纯fast-forward；该HEAD没有GitHub Actions运行；
- 生产边界：相对M03开始提交`32ed83f`，`.github/workflows/`、`public/`、`automation/`、网站应用和Worker均零变化。

<a id="m03-acceptance-report-zh-2026-09-01集成冒烟修复复核"></a>
### 2026-09-01集成冒烟修复复核

- 两项修复当前保存在独立分支，尚未合并`main`、推送或部署；M03既有生产状态没有改变。
- M01／M02／M03定向：76项通过；完整Python：460项通过。
- `PYTHONHASHSEED=0/1/42/12345`下M03定向25项每轮通过；Python编译通过。
- 前端lint、TypeScript检查、生产构建和11项测试通过；治理状态19项、补丁格式检查通过。
- A↔B循环即使旁边存在独立current，全部输入排列也失败关闭；合法A→B→C语义不变。
- 完整formal且零eligible时不调用行情读取，仍生成`0`个事件、全部上游原因守恒的GateScanAudit；formal缺失仍为`universe_unavailable`，未知原因仍失败关闭。
- 修复没有改变GateEvent门槛、formal／legacy隔离、生产默认入口、工作流、公开JSON、网站或Discord；M04和M12均未开始。

<a id="m03-acceptance-report-zh-关键反例"></a>
## 关键反例

- 没有当日精确MACD刚金叉时不创建GateEvent，只累计非事件原因；
- 影子结构不能把`production_effect`改成`true`，也不能改变`baseline_passed`；
- GateEvent 1.x不能进入formal消费者；formal缺失不会自动回退legacy；
- 错误复权政策、内容指纹、批次数量和同身份不同内容均失败关闭；
- 行情快照变化没有显式修订证据时失败；有证据时产生新事件并保留旧事件；
- 月线和周线不使用当前未完成周期；pivot复用既有右侧确认入口；
- 默认每日与回放仍走旧路径，两个新增影子入口对同一M02输入得到同一事件身份。
- 6名固定完整Universe样本中，M02只为2名eligible证券交付OHLCV，同时向M03交付4名未入深度检查证券的不可变资格原因；GateScanAudit得到5个非事件原因和1个事件，`input_count=6`且总数守恒。价格、历史和流动性资格不在M03重新计算，无法按M02事实可靠归类的排除证据失败关闭。
- 三代事件A→B→C在旧链输入为`[A, B]`或`[B, A]`时都让C替代唯一current B；分叉、断链、跨逻辑信号、循环、重复事件身份和修订证据未绑定直接前一事件均失败，不能按参数或文件顺序猜测。

<a id="m03-acceptance-report-zh-四个案例的证据纪律"></a>
## 四个案例的证据纪律

本地没有四只真实股票的完整点时行情缓存，因此没有伪造真实OHLCV或宣称完成收益验证。固定小样本只验证检测边界：

- CGEM式长期筑底与BTDR式宽幅箱体在精确阈值未单独批准时返回`unavailable`；
- MRNA式样本能够保存超过90%的多年深跌事实，但不自动否决基线；
- DLTR式样本能够保存向下缺口及未回补事实，但`production_effect=false`。

真实案例复核只能在未来获得可信点时数据后进行，且仍不得用来调参或证明收益。

<a id="m03-acceptance-report-zh-仍未完成未授权"></a>
## 仍未完成／未授权

- 未部署或生产启用GateEvent；
- 正式每日扫描和夜间回测尚未切换到M03；
- 网站、Discord、工作流和公开JSON尚未采用M03；
- 个人形态兼容留给M05；
- 因子、选股、上下文、排行、交易、总账和评价留给M04—M10；
- 工作流、Manifest、网站、Discord及线上回退留给M12。

本次合并及治理收口没有访问真实行情、运行真实每日任务、真实回测或发送Discord。M04和M12均未开始。

---

<a id="m04-acceptance-report-zh"></a>

## 原文件：M04_ACCEPTANCE_REPORT_ZH.md

<a id="m04-acceptance-report-zh-m04统一因子事实与-technicalevidence-本地验收报告"></a>
# M04｜统一因子事实与 TechnicalEvidence 本地验收报告

- CR：`CR-2026-09-01-044`
- 分支：`m04/technical-evidence-547949b`
- 基线：`547949bad8c3447aeeb7665723ed49178f8050f2`
- 状态：`implemented`（获批影子范围已进入`main`）
- 生产状态：未部署、未启用

<a id="m04-acceptance-report-zh-1-结论"></a>
## 1. 结论

M04获批范围已完成本地实现：M02不可变点时行情与M03 `GateEvent 2.x`可以通过唯一`services/factors/`生产器生成不可变、无评分的`TechnicalEvidence 2.x`。每日和回放影子入口调用同一函数；当前生产入口和结果保持原样。

<a id="m04-acceptance-report-zh-2-已完成"></a>
## 2. 已完成

- 新增唯一`TechnicalEvidence 2.x`生产器及批次身份。
- formal证据绑定GateEvent、instrument、Universe、行情快照、M02复权政策、注册表和检测政策。
- `macd.daily_bull_cross`与`qualification.long_trend`直接引用GateEvent事实。
- 其余因子复用现有唯一检测函数；固定样本逐项对照无差异。
- 每个注册表因子恰好生成一条证据，数量从注册表动态读取。
- 父子依赖分开保存`raw_hit`、`qualified_hit`和`blocked_by`，没有加入分数。
- 同一身份重放确定；内容篡改、身份篡改、重复或缺失因子均失败关闭。
- 旧快照只经一个适配器生成明确legacy 1.x视图，不补造formal身份，不改写源文件。
- 日终和回放只新增影子调用函数，没有接入默认任务。

<a id="m04-acceptance-report-zh-3-三个可人工检查的例子"></a>
## 3. 三个可人工检查的例子

1. `macd.daily_bull_cross`：证据的`source_kind=gate_reference`，其基线检查和`gate_event_id`直接来自M03，不在M04重新判断当前门票。
2. 普通检测因子：`available`、原始命中、最近命中日期、值和证据与旧`evaluate_all_factors`固定样本逐项相同；M04只增加身份和依赖解释。
3. 旧2026-08-28快照：所有已保存逐股因子可转换为带偏差标签的legacy视图；转换前后`public/daily-factor-snapshot.json`字节完全相同，不能进入formal 2.x入口。

<a id="m04-acceptance-report-zh-4-验证证据"></a>
## 4. 验证证据

- M04专项：14项通过。
- M01—M04定向：101项通过。
- 完整Python：474项通过。
- `PYTHONHASHSEED=0/1/42/12345`：每轮M04专项14项通过。
- Python编译：通过。
- 前端lint、TypeScript、生产构建：通过。
- 前端测试：11项通过。
- 补丁格式：通过。
- 测试前后只有本次批准范围内的文件变化，没有测试生成的意外文件。

<a id="m04-acceptance-report-zh-5-明确未改变"></a>
## 5. 明确未改变

- 没有修改因子ID、定义、阈值、注册表数量或研究状态。
- 没有修改MACD门票、GateEvent、股票池或行情事实。
- 没有计算或修改评分、权重、排行榜、精选门槛或交易计划。
- 没有修改`public/`、`automation/`、工作流、网站或Discord。
- 没有访问EODHD、运行真实每日任务或真实历史回测。
- 没有实现M05以后模块或M12生产集成。

<a id="m04-acceptance-report-zh-6-合并与尚未完成"></a>
## 6. 合并与尚未完成

- 三个提交为`46c5256`、`2fabbdc`、`545a411`，审核分支保留。
- 独立审核未发现可复现阻断缺陷；审核分支以纯fast-forward进入`main`，没有产生额外合并提交。
- 尚未部署或让生产消费者读取M04证据。
- 生产切换及真实发布证据仍属于M12。

因此本报告支持M04获批影子范围为`implemented`，但不能宣称已经部署或生产启用。

---

<a id="m05-acceptance-report-zh"></a>

## 原文件：M05_ACCEPTANCE_REPORT_ZH.md

<a id="m05-acceptance-report-zh-m05本地验收报告"></a>
# M05本地验收报告

状态：`implemented`（获批影子范围已通过独立审核并进入`main`；未部署、未生产启用）
基线：`dbb867202b5f0380c58d32190c9b68ff944233f2`
规则提交：`af8331d`
实现提交：`4f93eb3`
影子入口与测试提交：`12c554d`
独立审核修复提交：`8d0a999`
审核通过提交：`1793ecfe70a1c141b322b29dda827e7bd4dbc14f`

<a id="m05-acceptance-report-zh-完成范围"></a>
## 完成范围

- `services/selectors/`成为唯一新formal `ModelAssessment 2.x`身份生产层。
- 复杂多因子与个人形态从同一`GateEvent 2.x`和同一批`TechnicalEvidence 2.x`开始。
- 复杂多因子只整理证据引用、缺项和风险，不计算分数或排名。
- 个人形态V3专属事实使用`favorite_pattern.v3.*`身份并复用现有同一纯事实函数；共享事实不重算、不冒充。
- V1／V2和当前无需同日MACD的宽口径观察保持显式legacy只读。
- 每日与回放新增同源影子入口，默认生产入口和输出不变。

<a id="m05-acceptance-report-zh-关键反例"></a>
## 关键反例

- GateEvent、股票池、行情或TechnicalEvidence身份不一致失败关闭。
- 缺一项M04证据、证据批次被篡改或出现未知GateEvent失败关闭。
- legacy `ModelAssessment 1.x`不能进入formal 2.x消费者。
- 个人形态专属事实若使用共享因子ID冒充，验证失败。
- assessment身份或内容被篡改，验证失败。
- formal缺失不会自动改走legacy。
- 输出出现评分、权重、排名、市场／行业调整或交易计划字段，验证失败。
- 即使攻击者重算身份与内容指纹，`ModelAssessment 2.x`也不得改标为legacy；legacy只允许经1.x只读适配器表达。

<a id="m05-acceptance-report-zh-验收结果"></a>
## 验收结果

- M05专项：16项通过。
- M01—M05相关定向：106项通过。
- 完整Python：490项通过。
- `PYTHONHASHSEED=0/1/42/12345`：每轮55项通过。
- 治理状态：19项通过。
- Python编译：通过。
- 前端lint、TypeScript、生产构建：通过。
- 前端测试：11项通过。
- `git diff --check`：通过。
- 测试前后未产生意外文件或范围外变化。

<a id="m05-acceptance-report-zh-独立审核修复"></a>
## 独立审核修复

- 首次独立审核确认唯一当前阻断缺陷：公共合同验证器曾允许重新计算身份后的`ModelAssessment 2.x`携带legacy路径与偏差标签，虽然formal生产器本身不会生成该结果。
- 提交`8d0a999`在唯一共享合同入口失败关闭：2.x固定为formal且不得携带legacy偏差；新增公开验证入口反例，不增加第二套生产或兼容逻辑。
- 修复没有改变两个分析器的判断、M03／M04事实、旧1.x legacy适配、默认生产入口或任何生产输出。
- 独立定向复核在`1793ecf`未发现新的可复现阻断缺陷；M05提交链随后以纯fast-forward进入`main`。

<a id="m05-acceptance-report-zh-固定样本结论"></a>
## 固定样本结论

- 新formal个人形态事实与旧V3相同固定行情样本的四项命中、阶段和风险阻断一致。
- complex判断直接引用M04证据ID；未调用M03门卫或M04因子检测器重新计算。
- 每日与回放对同一输入得到相同assessment身份和内容。

<a id="m05-acceptance-report-zh-明确未完成"></a>
## 明确未完成

- 未部署或生产启用；正式每日、夜间、网站、Discord和公开JSON仍未消费M05影子产物。
- 未修改评分、排行、市场／行业、交易计划、总账或评价。
- 未修改工作流、网站、Discord、`public/`、`automation/`或生产缓存。
- M06—M10和M12均未开始。

---

<a id="m06-acceptance-report-zh"></a>

## 原文件：M06_ACCEPTANCE_REPORT_ZH.md

<a id="m06-acceptance-report-zh-m06市场与行业上下文本地验收报告"></a>
# M06｜市场与行业上下文本地验收报告

- 状态：`implemented`（获批影子范围已进入`main`）
- 基线：`f73512584bb412ddced3179a993fabee623a0b7a`
- 设计／规则提交：`c7f072a`
- 实现提交：`d97a74f`
- 测试提交：`d80744c`
- formal成分守恒修复：`187c0ec`
- 结论：影子成果和formal成分守恒修复已通过快速独立审核，完整审核链以纯fast-forward进入`main`；未部署或生产启用。

<a id="m06-acceptance-report-zh-已完成"></a>
## 已完成

- `services/context/`成为唯一formal `ContextSnapshot 2.x`生产层。
- 精选注册表登记`SPY`、`QQQ`、`IWM`、`XLE`、`SOXX`、`BOTZ`；未核实的`BOTT`和`XOXX`未登记。
- 现有2026-08-26官方成分证据只以ticker-only legacy索引登记，缺listing生命周期时formal失败关闭。
- ETF状态集中保存趋势、回调、接近／确认突破、结构走弱及原始数字证据，同一ETF每批只计算一次。
- 一只股可同时引用多个ETF；M03—M05身份和事实只读引用，没有重算。
- 每日和回放影子入口调用同一生产器，默认生产入口不变。

<a id="m06-acceptance-report-zh-独立审核修复"></a>
## 独立审核修复

独立审核发现原验证器只要formal快照至少有一名稳定身份成员，就会忽略`members_source_count`和`unresolved_member_count`。这使“来源33名、只解析1名”可能冒充formal完整覆盖。

`187c0ec`已在唯一`validate_membership_registry()`入口失败关闭：所有快照的来源总数与未解析数必须是非负整数，且必须满足`来源总数 = 已解析成员数 + 未解析数`。formal还必须零未解析、至少一名稳定身份成员、完整数量相等、`formal_eligible=true`并且无偏差标签。legacy仍可保存未解析成员，但必须数量守恒、保存非空bias，且不能被formal选择。

当前真实2026-08-26成分仍是ticker-only legacy证据。SOXX—AVGO固定合成样本只证明合同能正确处理完整身份，不代表真实行业连接已完成。

<a id="m06-acceptance-report-zh-验证证据"></a>
## 验证证据

| 检查 | 结果 |
| --- | --- |
| M06专项 | 15项通过 |
| M01—M06相关定向 | 138项通过 |
| 完整Python | 505项通过 |
| `PYTHONHASHSEED=0/1/42/12345` | 每轮M06 15项通过 |
| 治理状态 | 19项通过 |
| Python编译 | 通过 |
| 前端lint／TypeScript／生产构建 | 通过 |
| 前端测试 | 11项通过 |
| 文档链接／`git diff --check` | 通过 |

<a id="m06-acceptance-report-zh-固定反例"></a>
## 固定反例

- SOXX—AVGO、BOTZ及一股多ETF完整formal合成样本可生成客观上下文。
- 只有当前ticker的成分快照不能进更早formal回放；显式legacy携带`current_membership_bias`。
- ETF行情缺失、成分版本冲突、稳定身份缺失或legacy进formal时失败关闭。
- formal来源33名而只解析1名、formal含任何未解析成员，或任何路径数量不守恒时失败关闭；完整formal和现有数量守恒legacy继续通过。
- `as_of`之后的极端K线不能改变当日ETF状态。
- 输入顺序、每日／回放入口和四种哈希种子不改身份与内容。

<a id="m06-acceptance-report-zh-未改变的生产范围"></a>
## 未改变的生产范围

本包没有修改`.github/`、`public/`、`automation/`、网站、Discord、默认每日／夜间入口、MACD、因子、评分、排名、交易或历史结果。`production_effect=false`。M07和M12尚未开始。

<a id="m06-acceptance-report-zh-残余证据缺口"></a>
## 残余证据缺口

- 本地没有可用的真实ETF点时行情缓存，因此本轮不宣称完成真实市场全量复现。
- 2026-08-26成分证据缺可靠listing生命周期，只能作legacy证据。从未来完整保存稳定身份的成分日开始，formal才可向前追加。
- 真实生产缓存、Manifest、工作流、网站和Discord切换仍属M12，不属于M06缺陷。

---

<a id="m07-acceptance-report-zh"></a>

## 原文件：M07_ACCEPTANCE_REPORT_ZH.md

<a id="m07-acceptance-report-zh-m07版本化评分与唯一排行本地验收报告"></a>
# M07｜版本化评分与唯一排行本地验收报告

- 日期：2026-09-01
- 关联CR：`CR-2026-09-01-047`
- 状态：`implemented`（获批影子范围已进入`main`）
- 设计提交：`7fa6e59`
- 实现提交：`8a773e8`
- 测试提交：`4c1acdb`
- 行为等价修复提交：`405bd3e`
- 独立审核：首次发现近期命中兼容缺口；`405bd3e`修复后快速复核通过
- 审核与合并头：`2449856a67bc68b6f574fbbc247279c722a037f9`，纯fast-forward
- 部署、生产启用：均未发生

<a id="m07-acceptance-report-zh-验收结论"></a>
## 验收结论

M07获批的A—E影子范围已完成：`services/ranking/`是唯一formal `ScoreResult 2.x`和复杂多因子`RankingSnapshot 2.x`生产层。首个政策只复现旧技术共振颗数、家族、父子确认与跨周期奖金；M06上下文只保存引用，贡献固定为零。个人形态没有第二张主榜。

评分、排序和权威资格分别绑定版本与内容指纹。相同输入和政策稳定重放；完整排序键被保存，最终并列由稳定`instrument_id`裁决。缺失事实进入`unavailable`或明确排除，不会以零分继续排名。V2在批准生效日前只能生成引用原快照的`comparison`，不得冒充当时权威结果。

影子快照只允许写入系统临时目录或仓库内部受保护的`work/`，采用内容寻址和只追加冲突保护。旧排行JSON没有改写，生产Manifest、公开发布、永久存储和默认入口切换仍属于M12。

<a id="m07-acceptance-report-zh-固定反例"></a>
## 固定反例

- 旧技术共振分项和总分逐项等价。
- 旧排行指定因子的`recent_hit=true`且当日`hit=false`时，M07仍得到相同颗数、家族和总分；取值清单集中在评分政策内，不重新检测因子。
- 改变输入顺序不改变评分身份或排行。
- M06上下文不增加分数或改变排序。
- 缺失因子事实得到`unavailable`且不进入排行。
- 篡改分项、总分、排序或内容指纹失败关闭。
- 新政策在生效日前不能成为权威，只能生成不可混淆的`comparison`。
- 同日第二张不同权威快照被只追加存储拒绝。
- 旧排行只读适配前后字节不变，且不能进入formal消费者。
- 每日与回放影子入口调用同一生产器并得到相同身份。
- 唯一生产者清单确认没有第二个formal评分或排行身份创建入口。

<a id="m07-acceptance-report-zh-机械验证"></a>
## 机械验证

- M07专项：13项通过。
- M01—M07定向：162项通过。
- 完整Python：518项通过。
- `PYTHONHASHSEED=0/1/42/12345`：每轮13项通过。
- 治理状态：19项通过。
- 前端：lint、TypeScript、生产构建及11项测试通过。
- Python编译、文档链接和差异格式检查：通过。
- 测试前后：没有生成范围外版本控制变化。

<a id="m07-acceptance-report-zh-明确未做"></a>
## 明确未做

没有修改生产每日或夜间入口、工作流、网站、Discord、公开JSON、评分业务规则或旧历史结果；没有部署、真实行情、真实回测或生产排行。M08交易计划、M09总账、M10评价／Excel和M12生产接入均未开始。CR-043整体继续为`captured`。

进入`main`不等于部署或生产启用。

---

<a id="m08-acceptance-report-zh"></a>

## 原文件：M08_ACCEPTANCE_REPORT_ZH.md

<a id="m08-acceptance-report-zh-m08统一模拟交易计划与退出状态验收报告"></a>
# M08｜统一模拟交易计划与退出状态验收报告

- 日期：2026-09-01
- 关联CR：`CR-2026-09-01-048`
- 状态：`implemented`（仅获批影子范围；已独立审核并进入`main`）
- 设计提交：`c00e4e8`
- 实现提交：`cc42569`
- 测试提交：`75a4d3c`
- 验收证据提交：`43ccc22`
- 部署、生产启用：均未发生

<a id="m08-acceptance-report-zh-结论"></a>
## 结论

M08 A—E影子实现完成并经独立审核通过，四个M08提交已经纯fast-forward进入`main`。`services/execution/`是唯一formal `TradePlan 2.x`与`ExitState 2.x`身份生产层。首版只处理M07 `selected_entries`；未精选条目保留`not_selected_for_plan`，缺少下一调整后开盘或支撑证据时保留明确`unavailable`且不创建完整计划。

支撑由M04 `SupportEvidenceBatch`交付：现有唯一支撑计算结果绑定M02行情／股票池、M03 GateEvent、M04证据批次和三个稳定技术证据ID。M08没有导入或重新运行EMA、Fibonacci、pivot、Gate或因子检测，也不从M07分数或排行文字反推支撑。

计划明确标记`price_basis=provider_adjusted_ohlcv`，不是券商成交收据。退出状态机只复现跳空止损、普通止损、2R目标、40日到期及同日止损优先，并只保存模拟执行价；不计算收益、R收益、MFE、MAE或Excel。

<a id="m08-acceptance-report-zh-固定反例与行为等价"></a>
## 固定反例与行为等价

- 只有`selected_entries`创建计划；其他排行条目有唯一未建原因。
- 没有下一交易日真实调整后开盘时不创建计划。
- 新旧固定样本的入场、止损、2R目标和40日上限逐项相同。
- 同日止损与目标均触及时，新旧实现都先止损。
- 止损跳空使用当日开盘；普通止损和目标使用当日价格范围。
- 支撑证据直接绑定稳定M04 ID；篡改入场行情指纹或计划内容失败。
- 同一输入幂等，每日与回放影子入口得到相同批次身份。
- 退出状态只能追加；修改已经观察过的行情字节失败。
- legacy支撑视图不能进入formal计划生产器，适配前后原字节不变。
- 所有延后持仓、部分止盈、追踪和双退出实验保持关闭。

<a id="m08-acceptance-report-zh-机械验证"></a>
## 机械验证

- M08专项：13项通过。
- M01—M08主链：147项通过。
- 独立审核扩大定向：175项通过。
- 完整Python：531项通过。
- `PYTHONHASHSEED=0/1/42/12345`：每轮13项通过。
- 治理状态：19项通过。
- 前端：lint、TypeScript、生产构建及11项测试通过。
- Python编译、差异格式检查：通过。
- 测试前后：没有生成范围外版本控制变化。

<a id="m08-acceptance-report-zh-明确未做"></a>
## 明确未做

没有修改默认每日或夜间入口、工作流、网站、Discord、公开JSON、真实缓存或历史结果；没有访问EODHD、运行真实每日任务、真实多年回测、部署或发送通知。M09总账、M10评价／Excel、M12生产接入及所有`deferred_experiment`均未开始。

`implemented`只表示M08获批影子合同、唯一生产者、测试和验收证据已经进入主线；不表示部署或生产启用。

---

<a id="m09-acceptance-report-zh"></a>

## 原文件：M09_ACCEPTANCE_REPORT_ZH.md

<a id="m09-acceptance-report-zh-m09一本不可变事件总账本地验收报告"></a>
# M09｜一本不可变事件总账本地验收报告

- 状态：`implemented`（仅获批影子范围）
- 基线：`a4ce610f4addd28fca444f28ba38298e4a64199d`
- 规则／设计提交：`8818fa7a6911879002e0c5f679dda3b396b83aa4`
- 实现提交：`0d1c2526360b0753d0ca4f2fbec4013b8ee5c2fe`
- 测试提交：`7ca8ea37a0342fea3ed5e10887ca8053295d9040`
- 审核头：`1012b7e30262b2fdaf9433f0dd44ed40a29fa4b1`，已纯fast-forward进入`main`
- 生产状态：未部署、未生产启用

<a id="m09-acceptance-report-zh-1-验收结论"></a>
## 1. 验收结论

M09获批影子范围已经形成一套唯一、不可变、可追溯的事件总账基础并进入`main`：M07每个权威formal入榜记录建立一个事件根，M08后续计划和退出只以关联记录追加，人工审核也只追加且不能修改机器事实。三路快速独立审核在已批准范围内未发现剩余可复现阻断缺陷。

这不是生产迁移。旧Opportunity Ledger、Signal History、网站、Discord、每日／夜间工作流和公开JSON继续原样运行。

<a id="m09-acceptance-report-zh-2-用户批准项"></a>
## 2. 用户批准项

1. 权威formal `ranked_entries`全部建立事件；`selected`只决定M08是否尝试建立计划。
2. 入榜当天立即建立机器事件；下一交易日真实开盘出现后再追加M08计划关联。
3. 影子人工审核必须注入稳定非空`author_id`；账号、登录和权限系统留给M12。

<a id="m09-acceptance-report-zh-3-机械验收结果"></a>
## 3. 机械验收结果

| 验收项 | 结果 |
| --- | --- |
| 仅权威formal排行可建事件，comparison不能冒充 | 通过 |
| 同股同日只有一个根事件；模型、排行和计划变化只追加关联 | 通过 |
| 同一身份同一内容幂等；同一身份不同内容冲突失败 | 通过 |
| 所有M03—M08稳定ID、版本与内容指纹可追溯 | 通过 |
| 同Gate、同证券、同模型最多一份ModelAssessment | 通过 |
| 未精选、无计划或计划不可用的入榜事件仍保留 | 通过 |
| 人工记录要求作者、时间、类型、正文和真实关联对象 | 通过 |
| `approved_change`要求已知批准引用且不改变旧事件或政策 | 通过 |
| 旧账仅只读适配；ticker＋日期歧义不升级formal | 通过 |
| 每日与回放薄入口调用同一生产器并得到相同身份 | 通过 |
| 影子存储原子、只追加并拒绝生产目录 | 通过 |
| 收益、MFE／MAE、Excel、网站、Discord和生产接入零实现 | 通过 |

<a id="m09-acceptance-report-zh-4-旧账只读对账"></a>
## 4. 旧账只读对账

- `public/opportunity-ledger.json`：4,451条旧记录。
- `public/signal-history.json`：69条旧记录。
- 对账分类：明确ID匹配61、仅Opportunity 4,384、仅Signal 2、歧义6、冲突0。
- 适配器只读取原始字节；适配前后文件逐字节相同。
- 上述数字只是当前旧账样本审计，不表示旧记录已迁移为formal事件。

<a id="m09-acceptance-report-zh-5-验证记录"></a>
## 5. 验证记录

- M09专项：19项通过。
- M01—M09定向：194项通过。
- 完整Python：550项通过。
- `PYTHONHASHSEED=0/1/42/12345`：每轮19项通过。
- 治理状态：19项通过。
- 前端：lint、TypeScript、生产构建及11项测试通过。
- Python编译与差异格式检查：通过。
- 测试前后没有产生范围外文件。

<a id="m09-acceptance-report-zh-6-独立审核发现与修复"></a>
## 6. 独立审核发现与修复

快速审核发现M05批次验证器原先只拒绝重复`assessment_id`，仍可能接受同一Gate、证券和模型的两份各自合法判断，导致下游版本字典静默覆盖。修复只在现有唯一验证入口增加逻辑唯一键，并以两份合法身份、合法内容指纹和合法批次身份的反例证明失败关闭。复核后该缺口关闭。

其余审核分别确认：事件与关联记录身份不能交叉伪造；孤儿计划链接失败；人工作者、批准引用和关联对象必须真实；旧账歧义不猜测；没有引入收益、Excel或生产范围。

<a id="m09-acceptance-report-zh-7-明确未做"></a>
## 7. 明确未做

- 已纯fast-forward进入`main`；未部署、未生产启用。
- 未修改`public/`、`automation/`、工作流、网站、Worker或Discord。
- 未运行真实每日行情、真实回测或收益评价。
- 未生成Excel，未实现M10、M11或M12。
- CR-043整体继续为`captured`。

M09已按获批影子范围记为`implemented`；这仍不等于部署或生产启用。

---

<a id="m10-acceptance-report-zh"></a>

## 原文件：M10_ACCEPTANCE_REPORT_ZH.md

<a id="m10-acceptance-report-zh-m10内部评价与只读汇总阶段验收报告"></a>
# M10｜内部评价与只读汇总阶段验收报告

- 状态：M10-A／B／C／D／E均已完成独立审核并进入`main`；M10核心A—E在获批影子范围内为`implemented`
- 基线：`1c7f688bd0d3f0c52386851b302c6197f25437fb`
- Forward实现：`209d088045cd5c9d87be130a1c4b8499336cd202`
- Trade实现：`a81d97ce288f7b62224e08556145c93a41df4b5c`
- 运行收据与同源入口：`940604e8a004a2e2d0c54fbfeda1e7c6e8e3af65`
- 运行结果完整守恒修复：`cd1379cda5513a7f13393ec47f23adbf897effa2`
- ExitState与事件证券绑定修复：`3cecf80f0afd79d84b56518b6f0bb6644d984bcf`
- Forward日历证据绑定修复：`fc3f2b72d37b874719935263dc0f55e11b6fbdd8`
- completed落盘pending根修复：`2f3fe38489668a4aa2929a40bd4f0354dab9fffc`
- Forward窗口目标交易日绑定修复：`9282ffb33c6f3028620b8a36398b1079dc568e6c`
- 无未来目标与ForwardOutcome 2.1隔离修复：`6ac5465ac3b2209dd3f2d0304125e4d6c7342569`
- internal-baseline来源版本统一修复：`ea4b6f187888a1f31b6398556eaa39539538d5b7`
- 历史结果链来源混用封堵：`d99db58d108eb0c404df406d624fb1d543f0a58b`
- 最终审核代码HEAD：`108a29271c75ba6b49f1172350fc3adbf3460a25`
- 合并方式：纯fast-forward进入`main`
- M10-C设计冻结：`dbcdcf6`
- M10-C只读汇总生产层：`041e6be`
- M10-C边界回归测试：`a08dd33`
- M10-C审核代码HEAD：`7bb635617ddcfb06277d23269cca9fdfe4cadb8d`
- M10-C合并方式：纯fast-forward进入`main`
- M10-D设计冻结：`b90c269`
- M10-D基线：`3c0a314c921ffc38121a8ef678cf61be16bd2b86`
- M10-D原子查询与CSV：`e7c649f`
- M10-D锁定XLSX审核副本：`ee6d596`
- M10-D逐格一致与安全复核：`d682897`
- M10-D审核修复：`61de04e`
- M10-D审核通过代码HEAD：`f91a6fa5773561354b255f9217679f237b0f7017`
- M10-D合并方式：纯fast-forward进入`main`
- M10-E审核修复：`a0ab77c332995bb2710faa9d3ee946285c1cf0d1`
- M10-E terminal finalize修复：`7e2dcc0c66704d278974525eb4bdd33a4cd93ad1`
- M10-E最终审核代码HEAD：`34c3cfec1662ddd301552822eb919bb2dd84d12d`
- M10-E合并方式：纯fast-forward进入`main`
- 生产状态：未部署、未生产启用

<a id="m10-acceptance-report-zh-1-阶段结论"></a>
## 1. 阶段结论

M10-B已经用固定合成样本形成唯一内部基线评价层：ForwardOutcome从信号后下一有效交易日调整后开盘起算；TradeOutcome只读M08既有计划和退出事实；每次评价先绑定pending运行收据，结果通过后才追加complete收据。每日与回放影子入口调用同一生产器。

本报告还记录M10-C已经独立审核并进入`main`的Portfolio失败关闭边界和只读gross汇总能力。它不产生真实组合或多年回测结论；进入主线不代表生产接入或部署，且M10-C本身不承担M10-E编排或外部引擎责任。

M10-D已通过独立审核并以纯fast-forward进入`main`：唯一查询入口从`EvaluationShadowStore`取得原子库存，显式执行`all/current`修订语义并验证查询全集；CSV与XLSX逐字段绑定权威payload，完整包通过一次目录重命名发布，并由固定样式与标准库限定OOXML复核逐格对账。`ExportManifest`保存逻辑导出与实际物化证据，Human Review保持只出不进。

M10-E已通过最终极窄独立复核并以纯fast-forward进入`main`：`ResearchRunConfig 2.0.0`、统一非交互影子CLI、只追加checkpoint、显式续跑和并发编排共同复用M10-A—D公共入口。结果完整而completed收据写入失败时保留`pending + ready_to_finalize`，相同配置只重试finalize，不加载bundle或重跑生产器。M10核心A—E的`implemented`仅表示获批影子能力完成审核并进入主线，不表示部署、生产启用或真实回测。

<a id="m10-acceptance-report-zh-2-已验证口径"></a>
## 2. 已验证口径

| 验收项 | 结果 |
| --- | --- |
| Forward起点只用信号后下一有效交易日调整后开盘 | 通过 |
| 信号日收盘不作为起点；下一开盘缺失不回退其他价格 | 通过 |
| 日历只保存不晚于`as_of`的已发生session前缀；未成熟窗口的目标日和端点均为`null` | 通过 |
| 成熟窗口目标日严格等于已发生session前缀的第N日；端点日期和价格必须来自该日历对应行 | 通过 |
| 旧ForwardOutcome 2.0.0按原字段只读；新formal生产和完成流程只接受严格ForwardOutcome 2.1.0 | 通过 |
| 未成熟窗口为pending；到期缺证据为partial或unavailable | 通过 |
| Forward MFE／MAE只使用已成熟且完整的窗口证据 | 通过 |
| Trade只读M08入场、止损、目标、40日和同日止损优先结果 | 通过 |
| Trade毛收益、R收益和持有交易日数可复核 | 通过 |
| formal净收益因费用／滑点未批准保持unavailable | 通过 |
| 零成本净收益只允许明确comparison | 通过 |
| Trade MFE／MAE均为unavailable，写入数值验证失败 | 通过 |
| pending成熟只追加修订，旧记录不覆盖 | 通过 |
| ExperimentRun输入、结果引用及收据修订守恒 | 通过 |
| pending收据冻结事件、证券、日期、行情、股票池、规范化日历ID与实际session内容指纹、计划、ExitState及预期逻辑结果；五个Forward窗口必须绑定同一日历证据，complete拒绝缺少、重复、多出、外来或换指纹结果 | 通过 |
| Forward每个事件完整保存1／5／20／60／100五个窗口，混合pending／partial／unavailable／mature状态也保持集合守恒 | 通过 |
| 内部基线completed必须在同一run锁内直接承接实际落盘的唯一pending链尾；仅有结果、无pending根或伪造未落盘前序均失败且旧字节不变 | 通过 |
| 新formal internal-baseline的pending收据、全部Forward／Trade结果和completed收据必须共同使用`m10-b-internal-1.1.0`；旧1.0仅通用合同只读，不能参与、追加或完成新运行 | 通过 |
| ExitState状态、退出原因、退出日期与执行价格一致；active不能伪造终态事实 | 通过 |
| M09事件、TradePlan、ExitState及两条机器链接的证券和信号日完全一致 | 通过 |
| 每日与回放相同输入得到相同结果和运行身份 | 通过 |
| M02—M09输入在评价前后不变 | 通过 |

<a id="m10-acceptance-report-zh-3-验证记录"></a>
## 3. 验证记录

- M10合同与基线专项：78项通过；M08与M10专项：93项通过。
- M01—M10扩大定向（含M02行情仓）：274项通过。
- 完整Python：630项通过。
- `PYTHONHASHSEED=0/1/42/12345`：每轮93项通过。
- 机械版本攻击及最终四闸门：11项通过。
- 治理状态：19项通过。
- 前端：lint、TypeScript、生产构建及11项测试通过。
- Python编译、文档链接和差异格式检查：通过。
- 新增机械回归证明：日历拒绝晚于`as_of`的session；5、19、59、99个已发生session时未成熟窗口目标日保持`null`，第20／60／100个session实际发生后才首次写入对应目标日。旧2.0.0不允许2.1.0字段且不能进入新formal完成流程；新2.1.0强制包含可空目标日字段，混合版本不能complete。1／5／20／60／100任一窗口换成错误但合法的已发生日历日期，或端点日期正确但使用相邻日价格，均不能complete；明确的5日端点`2026-09-09`改为`2026-09-08`并重建合法结果身份仍失败关闭。目标日行情缺失不回退前后价格；合法五窗口、成熟修订、每日／回放同源及幂等重放继续通过。原有日历指纹、落盘pending根、结果全集、ExitState及事件证券绑定反例继续拒绝。
- 来源版本机械回归证明：pending 1.0＋Outcome 1.1、pending 1.1＋Outcome 1.0、五个Forward结果中仅一个为1.0、以及completed单独降为1.0，即使重新生成稳定身份和内容指纹也全部失败；公共影子存储同样拒绝混合版本且失败后旧字节不变。历史1.0结果即使已经存在，也不能被新1.1生产器或公共存储追加为同一修订链。完整1.1 pending→Outcome→completed及幂等重放继续通过；旧1.0收据仍可由通用合同只读验证，但不能写入或进入新formal运行。
- 测试前后没有出现范围外文件。

<a id="m10-acceptance-report-zh-4-m10-c独立审核与主线验收"></a>
## 4. M10-C独立审核与主线验收

| 验收项 | 结果 |
| --- | --- |
| `PortfolioRun 2.1.0`只接收已重新验证的TradeOutcome对象，引用规范排序且输入顺序不改变身份 | 通过 |
| 未批准资本政策时Portfolio恒为`unavailable/capital_allocation_policy_not_approved`，禁止收益、资金、仓位、曲线、回撤或改名指标 | 通过 |
| `ResearchAggregate 2.1.0`只消费一种完整的Forward或Trade结果对象，重新验证ID、内容指纹、逻辑链及共同口径 | 通过 |
| Forward严格区分`pending/mature/partial/unavailable`；Trade严格区分`completed/open/no_trade/unavailable` | 通过 |
| Trade `open`只从已验证的`pending + trade_open`映射，与`no_trade`分别计数，两者都进入missing而不当作零收益 | 通过 |
| `total=sum(status_counts)=evaluated+missing`且`win+loss+flat=evaluated` | 通过 |
| 空样本、无亏损、无盈利、全零、NaN／Infinity及PF量化边界 | 通过 |
| 生产和验证共用Decimal、`1e-10`和`ROUND_HALF_EVEN`；`gross_expectancy`与平均毛收益保持同一公式 | 通过 |
| 公共影子存储在同run锁内要求完整来源结果并重算守恒；重签统计、状态伪装、错误`as_of`和failed收据均失败且旧字节不变 | 通过 |
| 旧Portfolio／Aggregate `2.0.0`仅通用合同只读；新formal生产、运行和存储只接受`2.1.0`+`m10-c-readonly-1.0.0` | 通过 |

- M10-C专项：27项通过；M10合同／基线／汇总：105项通过；M08与M10：120项通过；指定含M09集合：139项通过。
- M01—M10扩大定向：290项通过；完整Python：657项通过。
- `PYTHONHASHSEED=0/1/42/12345`：M10-C每轮27项通过。
- 治理状态：19项通过；前端lint、TypeScript、生产构建和11项测试通过。
- Python编译、文档链接和差异格式检查通过；测试前后工作区没有意外文件。

<a id="m10-acceptance-report-zh-5-m10-d独立审核与主线验收"></a>
## 5. M10-D独立审核与主线验收

| 验收项 | 结果 |
| --- | --- |
| `EvaluationQuery 2.0.0`强制显式`revision_mode=all/current`；`current`先验完整修订链、选择唯一叶节点再过滤 | 通过 |
| 查询与写入共享store级inventory锁；锁顺序固定，查询只看到完整旧库存或完整新库存 | 通过 |
| 坏合同、坏ID／指纹、未知版本、断链、分叉、循环和ticker歧义失败关闭 | 通过 |
| M10-D启用前没有历史库存证据时返回`historical_inventory_unavailable`，不按时间戳猜历史 | 通过 |
| CSV使用UTF-8无BOM、RFC 4180／CRLF、固定列序与稳定行序；`audit_cell_codec_v1`可逆区分null、空串、0、false和真实`\\N` | 通过 |
| 每part最多1,000,000数据行；小阈值分片无丢失、重复或截断，各dataset独立守恒 | 通过 |
| `XlsxWriter==3.2.9`只锁入独立研究导出依赖；wheel／sdist哈希和BSD-2-Clause许可证证据已冻结 | 通过 |
| XLSX启用`constant_memory`并关闭公式、URL和数字自动转换；Decimal显示值与canonical text并列，不能安全往返时不伪造数值 | 通过 |
| 标准库限定OOXML复核真实sheet顺序、工作表范围、单元格类型及CSV逐格一致；公式、外链、未知cell和重签篡改失败 | 通过 |
| 没有来源行的结果表不生成；Score／Factor／Pair Matrix只在Coverage标记`not_implemented` | 通过 |
| `ExportManifest 2.0.0`区分稳定`export_id`与物化`export_receipt_id`，绑定来源、配置、逐part行数、字节数及SHA-256 | 通过 |
| 临时包写完、重读、校验、fsync后一次重命名；故障、路径逃逸、符号链接和已有导出冲突不留下半包 | 通过 |
| Human Review只出不进；人工修改使SHA失效，CSV／XLSX没有回写M10的入口 | 通过 |

独立审核随后复现了五个会影响导出数字可信度的阻断点，本分支以窄修复关闭：查询复核现在必须从同一冻结库存内嵌的规范payload重新执行唯一查询推导，缺少该证据明确返回`inventory_evidence_unavailable`；导出包验证从已验证payload重新生成全部主表和引用子表并逐表头、列序、行序和单元格精确对账；OOXML复核改为命名空间感知的固定结构／关系白名单并拒绝全部公式载体、外链、DDE／OLE、宏和异常ZIP成员；`styles.xml`及单元格style角色使用固定XlsxWriter 3.2.9白名单，额外或隐藏格式即失败；`export_receipt_id`由完整Manifest物化语义统一重算，外部传入ID不受信任。上述修复没有处理列宽、分页或66页等非阻断可读性问题。

- M10-D专项：25项通过；M10 A—D相关定向：130项通过；M08—M10：164项通过。
- M01—M10扩大定向：315项通过；完整Python：682项通过。
- `PYTHONHASHSEED=0/1/42/12345`：M10-D每轮25项通过。
- 治理状态：19项通过；前端lint、TypeScript、生产构建和11项测试通过。
- Python编译、隔离依赖完整性、文档链接和差异格式检查通过；测试前后工作区没有意外文件。
- 五项审核修复后：M10-D专项33项、M10 A—D相关定向138项、完整Python 690项通过；四种固定`PYTHONHASHSEED`下M10-D每轮33项通过。治理19项、前端11项、Python编译、独立XlsxWriter依赖证据、lint、TypeScript、生产构建、文档链接及格式检查通过。
- 最终独立审核的五个闸门全部通过，原始六项完整重签攻击全部失败关闭；43个本地文档链接通过。审核代码HEAD为`f91a6fa5773561354b255f9217679f237b0f7017`，已纯fast-forward进入`main`。

<a id="m10-acceptance-report-zh-6-m10-e本地验收"></a>
## 6. M10-E本地验收

| 验收项 | 结果 |
| --- | --- |
| `ResearchRunConfig 2.0.0`严格JSON、稳定身份、单一结果族与formal Git边界 | 通过 |
| `ResearchRunCheckpoint 2.0.0`只追加、完整集合守恒及显式续跑 | 通过 |
| pending先落盘，结果完整保存后才可terminal；公共存储无旁路 | 通过 |
| Forward／Trade／Portfolio-unavailable／ResearchAggregate只复用M10-A—D公共入口 | 通过 |
| 相同配置并发最多一条权威链；中断和异常不遗留死锁 | 通过 |
| CLI stdout唯一稳定JSON摘要，诊断写stderr，摘要与落盘证据一致 | 通过 |
| 可选M10-D导出失败与已完成评价隔离且不留下半包 | 通过 |
| M10-C输入由配置指定store解析，裸bundle Outcome在pending前失败 | 通过 |
| 异常后统一从磁盘重盘点work unit、结果、checkpoint和收据 | 通过 |
| checkpoint只表达`in_progress/ready_to_finalize`，ExperimentRun唯一表达终态 | 通过 |
| 结果完整但completed收据写入失败时保留`pending + ready_to_finalize`，同配置只重试finalize | 通过 |
| M10-E整数语义拒绝bool、float、字符串和Decimal冒充 | 通过 |
| 默认生产入口、旧回放断点、网站、Discord和公开JSON零变化 | 通过 |

- 提交：设计`2517fa6`、E1配置合同`b22da0a`、E2／E3编排实现`dbde7fc61c1dcac0959c838552b23051d114b361`、审核修复`a0ab77c332995bb2710faa9d3ee946285c1cf0d1`，以及completed收据只重试finalize修复`7e2dcc0c66704d278974525eb4bdd33a4cd93ad1`。
- 最终修复后M10-E专项40项、M10 A—E相关定向178项（跳过10项）、M01—M10扩大定向363项（跳过10项）及完整Python 730项（跳过10项）通过。
- `PYTHONHASHSEED=0/1/42/12345`下M10-E每轮40项通过；治理19项和前端11项通过。
- Python编译、lint、TypeScript、生产构建、文档链接及差异格式检查通过；测试前后工作区没有意外文件，旧生产断点字节不变。
- 空store裸Forward／Trade Outcome均在pending前拒绝；真实落盘来源在bundle/query路径得到同一结果。生产器保存5项后抛错时，failed收据、checkpoint和CLI摘要均从磁盘报告5项。全部结果完整且checkpoint为`ready_to_finalize`后，completed收据写入前失败或持续不可写均只保留`pending`及`terminal_persisted=false`，不再误写failed；写入后抛错会重读并按已落盘completed返回。同配置重试不加载bundle、不调用生产器，只重试finalize，并发最多形成一个terminal叶节点。
- 最终极窄复核确认五个terminal finalize闸门全部通过；M10-E随审核代码HEAD`34c3cfec1662ddd301552822eb919bb2dd84d12d`纯fast-forward进入`main`。M10核心A—E在获批影子范围内为`implemented`。

<a id="m10-acceptance-report-zh-7-明确未做"></a>
## 7. 明确未做

- 未实现Portfolio资本、仓位、现金、权益曲线或风险算法；M10-C只产生明确`unavailable`的Portfolio边界。
- 未实现读取行情或重算逐股收益的研究算法；ResearchAggregate只读已冻结的`gross_return`。
- 未安装或接入VectorBT；`XlsxWriter==3.2.9`仅存在于被忽略`work/`中的隔离研究导出环境和独立锁文件，不进入生产依赖。
- 未创建看板；M10-E CLI和M10-D CSV／XLSX均只使用固定合成样本及临时目录验收，没有提交生成文件。
- 未运行真实行情、真实每日任务或真实多年回测。
- 未修改生产入口、工作流、网站、Discord、公开JSON或历史断点。
- 未开始VectorBT X1／X2／X3、M11、M12或M13。

M10-A／B／C／D／E均已完成独立审核并进入`main`，M10核心在获批影子范围内为`implemented`。这不等于部署、生产启用或完成真实历史导出；`python3 -m research.run --config <versioned-config.json>`仍是未被生产工作流调用的影子统一入口。正式每日、夜间、网站和Discord继续使用旧路径，M12才负责生产Manifest与工作流切换。2026-08-28及更早formal股票池证据仍不足，不能宣称正式多年收益；尚未生成正式生产CSV／XLSX，网站没有研究看板或下载入口。Portfolio资本算法和VectorBT X1／X2／X3均未实现；Excel仍是人工审核副本，人工修改不能回写M10权威账本。M11、M12和M13均未开始，也未访问EODHD或运行真实行情／真实多年回测。

---

<a id="m11-acceptance-report-zh"></a>

## 原文件：M11_ACCEPTANCE_REPORT_ZH.md

<a id="m11-acceptance-report-zh-m11策略验证批准与退休闸门本地验收"></a>
# M11｜策略验证、批准与退休闸门本地验收

状态：`verified`（仅本地合成验收；等待全新独立审核，审核分支）

验收日期：2026-09-06

对应需求：`CR-2026-09-05-051`

<a id="m11-acceptance-report-zh-2026-09-06-criterion身份自证修复"></a>
## 2026-09-06 criterion身份自证修复

- 审核基线：`751cc3ebfe4cf5ba3342c503baaac648047d1e72`。基线实测：固定合成baseline criterion分别使用`forward_outcome_id`和`forward_content_fingerprint`，expected填实际结果ID／指纹，经合成可信预登记后均为`validated`，`write_proposal`和`write_assessment`均接受。
- 修复只在`services/playbook/contracts.py`的预登记合同入口集中增加四种结果合同的业务字段、数值类型及封闭状态枚举允许表；未修改消费者。规则11升级`1.2.1`，schema和来源版本不变，不重写历史。
- 两个反例覆盖构造器、直接合同验证、评估、公共Proposal写入，以及模拟旧漏洞写入的canonical Proposal被重新读取时的公共Assessment写入；均应在criterion验证处拒绝。
- 合法状态、指标eq/gte/lte和计数可评估并落盘；错误类型、等价身份／指纹字段、自由文本与嵌套路径拒绝。零匹配仍unavailable，多匹配失败关闭，旧2.0／2.1只读边界由既有专项回归覆盖。
- 本轮验证：M11专项60项通过；完整Python运行790项，780通过、10跳过；PYTHONHASHSEED=0／1／42／12345每轮60项通过；前端11项、lint、TypeScript、生产构建、Python编译、变更文档链接与`git diff --check`通过。机器状态重新生成内容与CURRENT_STATUS完全一致。以下历史测试数字属于先前收口，并非本次独立审核结论。
- 提交证据：本节与修复代码同属独立提交`fix: restrict M11 criteria to typed business fields`（父提交751cc3e）；最终完整SHA由交付消息及Git记录提供。审核分支`m11/strategy-promotion-gate-5859d12`。
- 仅本地合成样本；没有审核bot数据、合并、部署、真实策略晋级或生产启用。完成后留在审核分支，交全新独立审核。

<a id="m11-acceptance-report-zh-先前验收结论"></a>
## 先前验收结论

M11 A—D已在获批影子范围完成本地固定合成样本验证。本结论不代表合并`main`、真实策略有效、部署或生产启用。

<a id="m11-acceptance-report-zh-唯一生产层与合同"></a>
## 唯一生产层与合同

- 唯一实现位于`services/playbook/`。
- 当前formal写入使用`StrategyProposal 2.2.0`、`StrategyEvidenceAssessment 2.2.0`和`StrategyLifecycleEvent 2.2.0`；旧`2.0.0／2.1.0`只读，不能进入新的formal评估或存储。
- `StrategyRegistrySnapshot 2.2.0`只是从前三类完整链可再生成的只读视图，不保存第二份最终状态；旧`2.0.0／2.1.0`同样只读。
- 实现、评估和生命周期记录均使用严格版本、规范化身份、内容指纹和线性只追加修订。

<a id="m11-acceptance-report-zh-机器证据闸门"></a>
## 机器证据闸门

- Proposal只允许已落盘M09 `hypothesis`或`approved_change`来源；`observation`不得直接晋级。2.2还必须绑定可信预登记记录，证明完整提议、证据范围和全部criterion早于每个相关M10 pending运行冻结。
- Assessment只从真实落盘的M09和M10影子存储重新读取并验证权威证据；未落盘对象、裸ID和仅格式合法的SHA不足够。
- 必须有completed ExperimentRun、完整结果集、formal无bias路径、数据／股票池／复权政策、候选／基线版本、全部预登记分区及至少一个独立`validation`或真实`forward`案例。
- 必需证据不足为`evidence_incomplete`；标准失败为`not_validated`，已验证后被新失败证据推翻则为`invalidated`。没有全局收益阈值。
- `case_label`和ticker只作显示；是否已见及validation／forward资格只由M09稳定事件身份和可信案例登记决定。换成已知ticker文字不会把未见案例变成已见，改成“UNSEEN”也不能隐藏真实已见案例。

<a id="m11-acceptance-report-zh-独立审核修复"></a>
## 独立审核修复

- 四项权威性修复及回归测试代码提交为`e63412817f1ee9dc36a2aa10cedf807fd71d2600`。
- 预登记现在冻结预期运行、必需分区／结果族／窗口、候选与基线版本、数据、股票池、政策及时间范围。Assessment从M10冻结库存确定性重推完整全集，再与声明逐项比较；遗漏不利运行、窗口或分区，增加／替换／重复运行，跨政策或跨结果族均失败关闭。
- Proposal案例角色绑定已落盘M09事件的`event_id`、稳定`instrument_id`、`signal_date`和内容指纹；`seen_before`由显式可信案例登记解析，显示标签、ticker别名和调用方声明不能改变案例身份或已见状态。
- 用户批准、main实现和M12激活事件必须经显式可信解析器重新验证。默认formal路径没有解析器即失败关闭；固定合成测试只能使用标记为`test`的解析器。M12尚未实施，因此真实formal `active`不可达。
- RegistrySnapshot在同一库存锁内从完整Proposal、Assessment和Lifecycle库存重建，并与待写入快照作规范字节比较；公共存储不能接受删项、增项、替换、重复或重签后的不完整快照。

<a id="m11-acceptance-report-zh-最终两项收口修复"></a>
## 最终两项收口修复

- 代码提交`ffda522`将current formal合同升级为严格`2.2.0`，来源版本升级为`m11-shadow-1.2.0`；`2.0.0／2.1.0`继续按原字段只读。
- `PreregistrationAuthorityResolver`必须返回完整、内容寻址的冻结记录，绑定完整Proposal业务语义、登记时间、登记提交及覆盖的M10运行代码提交。评估同时验证登记时间早于每个pending根`started_at`，并要求可信解析器确认登记提交先于对应运行提交；默认无解析器失败关闭。
- 2.2 criterion只允许以结果合同、candidate／baseline角色、分区、Forward窗口、字段、操作符和阈值作运行前语义选择；不得保存运行后才出现的Outcome ID或内容指纹。评估从M10完整库存匹配唯一结果，零匹配为证据不足，多匹配失败关闭，不重算收益或指标。
- `case_label`硬编码名单已退出合同判断；标签仍进入Proposal内容指纹，但不改变稳定案例身份、`seen_before`或案例资格。

<a id="m11-acceptance-report-zh-四轴和生命周期"></a>
## 四轴和生命周期

- 机器证据、用户决定、main实现和生产状态四轴独立。
- 用户可在尚未`validated`时批准候选实现，但不改写机器证据，也不能成为`active`。
- `implemented_in_main`必须具有精确代码提交、规则版本和测试证明，仍不等于生产。
- `active`还必须由M12提供Manifest、部署和线上验证证明；M11本轮未创建任何真实M12证明。
- 退休只追加并保留原active历史；已退休版本不得原地复活。V1与V2永久并存。

<a id="m11-acceptance-report-zh-测试证据"></a>
## 测试证据

- M11专项：54项通过。
- M09—M11联合定向：251项运行，241项通过、10项跳过。
- M01—M11扩大定向：417项运行，407项通过、10项跳过。
- 完整Python：784项运行，774项通过、10项跳过。
- `PYTHONHASHSEED=0／1／42／12345`：每轮54项通过。
- 治理合同：19项通过。
- 前端：11项通过；lint、TypeScript和生产构建通过。
- Python编译、文档链接和`git diff --check`通过。

<a id="m11-acceptance-report-zh-范围确认"></a>
## 范围确认

- 本轮没有读取行情、访问EODHD、运行真实实验／回测，也没有计算新指标。
- 没有改写M03—M10事实、规则、代码或生产配置。
- 没有修改网站、Discord、工作流、公开JSON或生产入口。
- M12、M13、VectorBT和看板均未开始。
- CR-043继续为`captured`。
- 当前真实formal validated、active和新增alpha hard rule数量均为0。
